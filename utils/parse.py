"""
Utilities for parsing HTML page data.
"""

from urllib.parse import urljoin

import bs4
from bs4 import BeautifulSoup

from api.client import BASE_URL

from .print import pprint
from .types import RegradeInfoDict


def parse_regrade_page(content: bytes | str) -> RegradeInfoDict:
    regrades_soup = BeautifulSoup(content, "html.parser")
    regrades_table = regrades_soup.select("table.js-regradeRequestsTable")[0]
    regrades_rows = regrades_table.select("tbody tr")

    regrade_info: RegradeInfoDict = {}

    # set of all review links associated with each student; used for deduplication
    student_review_links: dict[str, set[str]] = {}

    for row in regrades_rows:
        cur_cols = row.select("td")

        name_col = cur_cols[0]
        question_col = cur_cols[2]
        grader_col = cur_cols[3]
        review_col = cur_cols[5]

        # get the student name
        student_name = name_col.text
        if student_name not in regrade_info:
            regrade_info[student_name] = {
                # total number of comments submitted (could be multiple per question)
                "num_comments": 0,
                # regrades submitted (one for each question, with possibly multiple comments per question)
                # the length of this list is the number of unique questions the student submitted regrades for
                "regrades": [],
                # summary information; defaults to 0 here, to be filled in later on
                "num_accepted": 0,
                "num_responded": 0,
            }
        if student_name not in student_review_links:
            student_review_links[student_name] = set()

        # get the question title/link
        question_link_tag: bs4.Tag = question_col.find("a")
        if not question_link_tag:
            pprint("[red]ERROR: question link not found[/red]")
            continue
        question_relative_link: str = question_link_tag.get("href")
        question_title = question_link_tag.text

        # get the grader
        grader = grader_col.get_text(strip=True)

        # get the review link
        review_link_tag: bs4.Tag = review_col.find("a")
        if not review_link_tag:
            pprint("[red]ERROR: review link not found[/red]")
            continue
        review_relative_link: str = review_link_tag.get("href")
        review_absolute_link = urljoin(BASE_URL, review_relative_link)

        # add one to the number of comments, regardless of whether the review link is unique
        regrade_info[student_name]["num_comments"] += 1

        if review_absolute_link in student_review_links[student_name]:
            # skip this row, since we've already looked at this regrade chain
            continue
        student_review_links[student_name].add(review_absolute_link)

        # save info
        regrade_info[student_name]["regrades"].append(
            {
                "question": question_title,
                "grader": grader,
                "question_link": urljoin(BASE_URL, question_relative_link),
                "review_link": review_absolute_link,
            }
        )

    return regrade_info
