import datetime
import json
import re
from concurrent.futures import ProcessPoolExecutor
from functools import partial
from typing import Any, Optional, cast
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from rich.progress import Progress, track
from rich.prompt import Prompt
from rich.status import Status

from api.client import BASE_URL, GradescopeSession
from utils.cache import check_cache, load_cache, save_cache
from utils.parse import parse_regrade_page
from utils.print import (
    CONSOLE,
    plot_student_stats,
    pprint,
    print_request_details,
    print_staff_stats,
    print_student_stats,
)
from utils.types import (
    LinkMap,
    PrintOptions,
    RegradeInfoDict,
    RegradeRequest,
    ReviewData,
)

CLASSIFIER = None


def initialize_classifier():
    """
    Initialize the global classifier.

    Includes scoped imports to avoid unnecessary dependencies when classification is off.
    """
    # pylint: disable-next=import-outside-toplevel
    from transformers import pipeline  # for classification

    # pylint: disable-next=global-statement
    global CLASSIFIER

    CLASSIFIER = pipeline("zero-shot-classification", model="roberta-large-mnli")
    # CLASSIFIER = pipeline("zero-shot-classification", model="facebook/bart-large-mnli")


def format_request(regrade_request) -> list[RegradeRequest]:
    reviews: list[RegradeRequest] = []
    if regrade_request is None:
        return []

    if regrade_request["student_comment"] is not None:
        reviews.append(
            {
                "user": "student",
                "text": regrade_request["student_comment"],
                "timestamp": datetime.datetime.fromisoformat(
                    regrade_request["created_at"]
                ).timestamp(),
            }
        )
    if regrade_request["staff_comment"] is not None:
        reviews.append(
            {
                "user": "staff",
                "text": regrade_request["staff_comment"],
                "timestamp": datetime.datetime.fromisoformat(
                    regrade_request["updated_at"]
                ).timestamp(),
            }
        )
    return reviews


def get_review_data(cookies, link) -> ReviewData:
    # visit the review page
    review_response = requests.get(link, cookies=cookies, timeout=20)
    review_content = review_response.content

    # scrape the review page for any comments
    review_page_soup = BeautifulSoup(review_content, "html.parser")
    data_div = review_page_soup.select_one("div[data-react-class=SubmissionGrader]")
    if data_div is None:
        pprint(f"[red]ERROR: data div not found in {link}[/red]")
        return {
            "link": link,
            "reviews": [],
            "score": 0.0,
            "weight": 0.0,
            "accepted": None,
        }

    props_data = json.loads(cast(str, data_div.get("data-react-props")))
    open_request = props_data["open_request"]
    closed_requests = props_data["closed_requests"]

    reviews = [*format_request(open_request)]
    for closed_request in closed_requests:
        reviews.extend(format_request(closed_request))

    reviews.sort(key=lambda r: r["timestamp"])

    # get grading data
    score = float(props_data["submission"]["score"])
    weight = float(props_data["question"]["weight"])

    return {
        "link": link,
        "reviews": reviews,
        "score": score,
        "weight": weight,
        # default None; replaced later after classification
        "accepted": None,
    }


def get_all_review_data(cookies, links, num_processes=10) -> LinkMap:
    pool = ProcessPoolExecutor(num_processes)
    link_map: LinkMap = {}
    map_it = pool.map(partial(get_review_data, cookies), links)

    for result in track(
        map_it, total=len(links), description="Scraping review links..."
    ):
        link_map[result["link"]] = result

    return link_map


def get_metric(data, metric: str) -> int:
    if metric == "total":
        return data["num_comments"]
    if metric == "unique":
        return len(data["regrades"])

    # default use total
    return data["num_comments"]


def classify_responses(responses: list[str]) -> list[bool]:
    """
    Classify a list of regrade responses by staff as either accepted (True) or rejected (False).
    """
    assert CLASSIFIER is not None, "Classifier is not initialized yet."

    labels = ["accepted", "rejected"]
    hypothesis_template = "The request for additional credit was {}."

    results = cast(
        list[dict[str, Any]],
        CLASSIFIER(responses, labels, hypothesis_template=hypothesis_template),
    )

    final_results = []
    for result in results:
        # labels/scores are sorted already, from largest to smallest
        result_labels = result["labels"]
        result_scores = result["scores"]

        # only say that the request was accepted if it was fairly confident about it
        if result_labels[0] == "accepted" and result_scores[0] >= 0.6:
            final_results.append(True)
        else:
            final_results.append(False)

    return final_results


def modify_with_classifications(link_map: LinkMap):
    """
    Modify the `link_map` in-place with classification data for all staff responses.
    """

    # (link, index, text)
    data_to_classify: list[tuple[str, int, str]] = []

    for link, review_data in link_map.items():
        conversation = review_data["reviews"]
        for idx, info in enumerate(conversation):
            if info["user"] == "staff":
                data_to_classify.append((link, idx, info["text"].strip()))

    # in case the response was empty, default to text to indicate the request was accepted (which is generally the case)
    text_only = [data[2] or "accepted" for data in data_to_classify]

    with Progress(transient=True) as progress:
        progress.add_task("Classifying responses...", start=False, total=None)
        results = classify_responses(text_only)

    assert len(data_to_classify) == len(results)

    # modify link map
    for input_data, result in zip(data_to_classify, results):
        link = input_data[0]
        idx = input_data[1]

        review_data = link_map[link]

        if review_data["weight"] > 0 and review_data["score"] >= review_data["weight"]:
            # override result if the student got (at least) full score;
            # in this case the regrade request must have been accepted
            # (otherwise the student wouldn't have requested one in the first place)
            result = True
        elif review_data["weight"] > 0 and review_data["score"] <= 0:
            # override result if the student has zero points after the staff responded;
            # in this case the regrade request must have been rejected
            # (otherwise the student would have gained a positive number of points)
            result = False

        review_data["reviews"][idx]["accepted"] = result

    # aggregate to get whether the entire question was accepted/rejected
    for link, review_data in link_map.items():
        last_response_time = None
        last_response_accepted = False
        for review in review_data["reviews"]:
            if review["user"] == "staff":
                if (
                    last_response_time is None
                    or last_response_time < review["timestamp"]
                ):
                    last_response_time = review["timestamp"]
                    last_response_accepted = review.get("accepted", False)

        if last_response_time is not None:
            # classify as accepted if last staff response was classified as accepted
            review_data["accepted"] = last_response_accepted
        else:
            # if no responses, keep it as None
            review_data["accepted"] = None


def main(
    url: Optional[str] = None,
    cookie_file="cookies.json",
    cache_folder: Optional[str] = "cache",
    refresh_cache: bool = False,
    min_requests=0,
    metric="total",
    num_processes=10,
    classify=True,
    print_options: PrintOptions = PrintOptions.default(),
):

    # start with the given URL or ask via a prompt
    regrade_url: str = url or Prompt.ask("Gradescope regrade URL", console=CONSOLE)
    course_id: str
    assignment_id: str
    while True:
        url_match = re.match(r".*/courses/(\d+)/assignments/(\d+)", regrade_url)

        if not url_match:
            pprint("[red]Invalid regrade URL[/red]")
            regrade_url = Prompt.ask("Gradescope regrade URL", console=CONSOLE)
        else:
            course_id = url_match.group(1)
            assignment_id = url_match.group(2)
            regrade_url = urljoin(
                BASE_URL,
                f"courses/{course_id}/assignments/{assignment_id}/regrade_requests",
            )
            break

    regrade_info: Optional[RegradeInfoDict] = None
    link_map: Optional[LinkMap] = None

    loaded_from_cache = False
    cache_file = None
    if cache_folder is not None and not refresh_cache:
        cache_file = check_cache(cache_folder, course_id, assignment_id)
        if cache_file is not None:
            regrade_info, link_map = load_cache(cache_file)
            loaded_from_cache = True

    if loaded_from_cache:
        # cache file must have been specified
        pprint(
            f"[green]Cache hit: loaded data from cache at[/green] [blue]{cache_file}[/blue]"
        )
    else:
        if refresh_cache:
            pprint("[yellow]Forced cache miss: fetching data from Gradescope[/yellow]")
        else:
            pprint("[red]Cache miss: fetching data from Gradescope[/red]")

        driver = GradescopeSession(cookie_file=cookie_file)

        status = Status(f"Visiting [blue]{regrade_url}[/blue]", console=CONSOLE)
        status.start()
        regrade_url_response = driver.session.get(regrade_url)
        assert regrade_url_response.ok
        content = regrade_url_response.content
        status.stop()

        # fetch regrade info from table
        regrade_info = parse_regrade_page(content)

        review_links = set()

        # compile all review links together to fetch auxiliary data
        max_name_length = 0
        for name, student_data in regrade_info.items():
            info_list = student_data["regrades"]
            if get_metric(student_data, metric) >= min_requests:
                for info in info_list:
                    review_links.add(info["review_link"])
            max_name_length = max(max_name_length, len(name))

        # fetch details for each regrade request submitted
        link_map = get_all_review_data(
            driver.session.cookies, review_links, num_processes=num_processes
        )

        # get classification data for each regrade request
        if classify:
            initialize_classifier()
            modify_with_classifications(link_map)

        # count how many accepted regrade requests there were for each student
        for name, student_data in regrade_info.items():
            info_list = student_data["regrades"]

            num_questions_accepted = 0
            num_questions_responded = 0
            for info in info_list:
                review_data = link_map[info["review_link"]]

                if review_data["accepted"] is not None:
                    num_questions_accepted += review_data["accepted"]
                    num_questions_responded += 1

            student_data["num_accepted"] = num_questions_accepted
            student_data["num_responded"] = num_questions_responded

        if cache_folder is not None:
            # save data
            save_cache(cache_folder, course_id, assignment_id, regrade_info, link_map)

    # at this point all data should be loaded
    assert regrade_info is not None
    assert link_map is not None

    pprint("\n")

    # print regrade request contents
    if print_options.requests:
        print_request_details(regrade_info, link_map, metric, min_requests)

    pprint()

    if print_options.student_stats:
        print_student_stats(regrade_info, metric, min_requests)

    pprint()

    if print_options.staff_stats:
        print_staff_stats(regrade_info, link_map)

    if print_options.plot_student_stats:
        plot_student_stats(regrade_info, metric)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--url",
        default=None,
        action="store",
        type=str,
        help=(
            "Gradescope regrade requests URL. If invalid, the user is prompted to re-enter the URL."
            " Defaults to None, in which case the user is prompted."
        ),
    )
    parser.add_argument(
        "--cookies",
        action="store",
        default="cookies.json",
        help="Output file for saved cookies",
    )
    parser.add_argument(
        "--min-requests",
        action="store",
        type=int,
        default=0,
        help="Cutoff of regrade request count for display",
    )

    parser.add_argument(
        "--metric",
        choices=["unique", "total"],
        default="unique",
        type=str,
        help="Whether to use the number of unique questions that were requested ('unique'), or the total number of comments submitted ('total').",
    )

    parser.add_argument(
        "--parallel",
        "-p",
        default=10,
        type=int,
        help="Number of processes for parallel requests",
    )

    parser.add_argument(
        "--no-classify",
        action="store_false",
        dest="classify",
        help="Don't classify regrade requests as accepted/rejected. (Some printed statistics will be incorrect if this option is given.)",
    )

    parser.add_argument(
        "--cache",
        action="store",
        default="cache",
        type=str,
        help="Cache folder for requested regrade requests.",
    )
    parser.add_argument(
        "--refresh-cache",
        action="store_true",
        help="Refresh cache for the given regrade request link; force data to be requested again.",
    )

    print_info_args = parser.add_argument_group("print_info")
    print_info_args.add_argument(
        "--print-requests",
        action="store_true",
        help="Print all regrade request details.",
    )
    print_info_args.add_argument(
        "--print-student-stats",
        action="store_true",
        help="Print regrade request statistics for each student.",
    )
    print_info_args.add_argument(
        "--plot-student-stats",
        action="store_true",
        help="Plot student regrade request statistics.",
    )
    print_info_args.add_argument(
        "--print-staff-stats",
        action="store_true",
        help="Print regrade request statistics for each staff member.",
    )

    args = parser.parse_args()

    main(
        cookie_file=args.cookies,
        url=args.url,
        cache_folder=args.cache,
        refresh_cache=args.refresh_cache,
        min_requests=args.min_requests,
        metric=args.metric,
        num_processes=args.parallel,
        classify=args.classify,
        print_options=PrintOptions(
            requests=args.print_requests,
            student_stats=args.print_student_stats,
            plot_student_stats=args.plot_student_stats,
            staff_stats=args.print_staff_stats,
        ),
    )
