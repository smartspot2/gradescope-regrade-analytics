from rich import box
from rich.console import Console
from rich.padding import Padding
from rich.table import Table

from utils.types import LinkMap, RegradeInfo, RegradeInfoDict, StaffRegradeStatistics

CONSOLE = Console(highlight=False)


def pprint(*args, **kwargs):
    CONSOLE.print(*args, **kwargs)


def render_bar(fraction: float, bar_width=32):
    """Render a progress bar for the given fraction."""
    assert 0 <= fraction <= 1

    num_filled = int(bar_width * fraction)
    return num_filled * "█" + (bar_width - num_filled) * "•"


def render_percent_with_bar(count: int, total: int, bar_width=32):
    if total == 0:
        return "    NA%"

    fraction = count / total
    bar = render_bar(fraction, bar_width=bar_width)
    return f"{fraction:7.2%} {bar}"


def _get_metric(data: RegradeInfo, metric: str) -> int:
    """Fetch the given metric from the data."""
    if metric == "total":
        return data["num_comments"]
    if metric == "unique":
        return len(data["regrades"])

    # default use total
    return data["num_comments"]


def _get_sorted_student_names(
    regrade_info: RegradeInfoDict, sort_metric: str
) -> list[str]:
    """Sort names for printing by the given metric."""
    return sorted(
        regrade_info.keys(),
        key=lambda name: _get_metric(regrade_info[name], sort_metric),
    )


def print_request_details(
    regrade_info: RegradeInfoDict,
    link_map: LinkMap,
    sort_metric: str,
    min_requests: int,
):
    """
    Print all regrade request deatils.

    Parameters
    ----------
    regrade_info : RegradeInfoDict

        Regrade request information

    link_map : LinkMap

        Mapping from review links to detailed information about the regrade requests

    sort_metric : str

        Metric to sort results by.

    min_requests : int

        The minimum number of requests a student must have submitted in order to be displayed.

    """
    sorted_names = _get_sorted_student_names(regrade_info, sort_metric)

    TEXT_MAX_WIDTH = 120

    for name in sorted_names:

        student_data = regrade_info[name]
        info_list = student_data["regrades"]
        if len(info_list) < min_requests:
            continue

        title_text = ""
        if sort_metric == "unique":
            title_text = (
                f"[blue]{name}[/blue]: [red]{_get_metric(student_data, sort_metric)}[/red]"
                f" unique ([red]{_get_metric(student_data, 'total')}[/red] total)"
            )
        elif sort_metric == "total":
            title_text = (
                f"[blue]{name}[/blue]: [red]{_get_metric(student_data, sort_metric)}[/red]"
                f" total ([red]{_get_metric(student_data, 'unique')}[/red] unique)"
            )
        title_text += f"; [green]{student_data['num_accepted']}/{student_data['num_responded']}[/green] accepted"

        table = Table(
            title=title_text,
            title_justify="left",
            show_header=False,
            box=box.SIMPLE,
            title_style="bold",
        )
        table.add_column("Question", justify="right")
        table.add_column("Role", justify="right")
        table.add_column("Text", max_width=TEXT_MAX_WIDTH)

        for info in info_list:
            review_data = link_map[info["review_link"]]

            question_accepted = review_data["accepted"]
            if question_accepted is None:
                question_color = "yellow"
            elif question_accepted is True:
                question_color = "green"
            else:
                question_color = "red"

            question_text = f"[{question_color}]{info['question']}[/{question_color}]"
            grader_text = f"[grey53]{info['grader']}[/grey53]"

            first_row_wrapped = False
            for idx, review in enumerate(review_data["reviews"]):
                if review["user"] == "student":
                    role = "[yellow]STUDENT[/yellow]"
                    role_color = "yellow"
                else:
                    role = "[cyan]STAFF[/cyan]"
                    role_color = "cyan"

                text = f"[{role_color}]{review['text']}[/{role_color}]"

                if idx == 0:
                    # first review; add the question
                    if len(review["text"]) > TEXT_MAX_WIDTH or "\n" in review["text"]:
                        first_row_wrapped = True
                        question_text += "\n" + grader_text

                    table.add_row(question_text, role, text)
                elif idx == 1 and not first_row_wrapped:
                    # add grader if the first row did not wrap
                    table.add_row(grader_text, role, text)
                else:
                    # all other rows, do not add question
                    table.add_row("", role, text)

            if len(review_data["reviews"]) == 1 and not first_row_wrapped:
                # only one review, so the staff never responded; still add the grader in
                table.add_row(grader_text, "", "")

            # table.add_section()
        pprint(table)
        pprint()


def print_student_stats(
    regrade_info: RegradeInfoDict,
    sort_metric: str,
    min_requests: int,
):
    sorted_names = _get_sorted_student_names(regrade_info, sort_metric)
    sorted_names.reverse()

    table = Table(title=f"Student statistics (sorted by {sort_metric})")
    table.add_column("Name", style="blue")
    table.add_column("Total", style="cyan")
    table.add_column("Unique", style="cyan")
    table.add_column("Responded", style="yellow")
    table.add_column("Accepted", style="green")
    table.add_column("% Accepted (of responded)", style="green")

    # print statistics per student
    total_requests = 0
    total_unique_requests = 0
    total_accepted = 0
    total_responded = 0
    total_frac_accepted = 0
    total_students_with_responses = 0
    for name in sorted_names:
        student_data = regrade_info[name]
        info_list = student_data["regrades"]
        if len(info_list) < min_requests:
            continue

        total_requests += _get_metric(student_data, "total")
        total_unique_requests += _get_metric(student_data, "unique")
        total_accepted += student_data["num_accepted"]
        total_responded += student_data["num_responded"]

        if student_data["num_responded"] > 0:
            total_frac_accepted += (
                student_data["num_accepted"] / student_data["num_responded"]
            )
            total_students_with_responses += 1

        table.add_row(
            name,
            str(_get_metric(student_data, "total")),
            str(_get_metric(student_data, "unique")),
            str(student_data["num_responded"]),
            str(student_data["num_accepted"]),
            render_percent_with_bar(
                student_data["num_accepted"], student_data["num_responded"]
            ),
        )

    # Totals
    table.add_section()
    table.add_row(
        "[red]Total[/red]",
        str(total_requests),
        str(total_unique_requests),
        str(total_responded),
        str(total_accepted),
        render_percent_with_bar(total_accepted, total_responded),
    )

    pprint(table)

    if total_responded > 0:
        pprint(
            f"\n[cyan]{total_accepted}/{total_responded}[/cyan]"
            f" ([cyan]{total_accepted / total_responded * 100:.2f}%[/cyan]) regrades accepted"
        )
    if total_students_with_responses > 0:
        pprint(
            f"[cyan]{total_frac_accepted / total_students_with_responses * 100:.2f}%[/cyan]"
            " average acceptance rate among students"
        )


def print_staff_stats(regrade_info: RegradeInfoDict, link_map: LinkMap):
    # print statistics for each staff member
    staff_stats: dict[str, StaffRegradeStatistics] = {}
    for student_data in regrade_info.values():
        for regrade in student_data["regrades"]:
            staff_name = regrade["grader"]
            if staff_name not in staff_stats:
                staff_stats[staff_name] = {
                    "num_accepted": 0,
                    "num_responded": 0,
                    "num_requested": 0,
                }

            staff_stats[staff_name]["num_requested"] += 1

            question_accepted = link_map[regrade["review_link"]]["accepted"]

            if question_accepted is not None:
                staff_stats[staff_name]["num_responded"] += 1
                if question_accepted:
                    staff_stats[staff_name]["num_accepted"] += 1

    # sort staff by number requested (decreasing)
    sorted_names = sorted(
        staff_stats.keys(),
        key=lambda staff_name: staff_stats[staff_name]["num_requested"],
        reverse=True,
    )

    # do a first apss to see if we need the responded column;
    # we shouldn't show if it everything has 100% response rate
    show_responded_percent = False
    for stats in staff_stats.values():
        if stats["num_responded"] != stats["num_requested"]:
            show_responded_percent = True

    table = Table(title="Staff statistics")
    table.add_column("Name", style="blue")
    table.add_column("# Requested", style="cyan")
    table.add_column("# Responded", style="yellow")
    table.add_column("# Accepted", style="green")
    if show_responded_percent:
        table.add_column("% Responded (of requested)", style="yellow")
    table.add_column("% Accepted (of responded)", style="green")

    total_requested = 0
    total_responded = 0
    total_accepted = 0

    for staff_name in sorted_names:
        stats = staff_stats[staff_name]

        total_requested += stats["num_requested"]
        total_responded += stats["num_responded"]
        total_accepted += stats["num_accepted"]

        row = [
            staff_name,
            str(stats["num_requested"]),
            str(stats["num_responded"]),
            str(stats["num_accepted"]),
        ]

        if show_responded_percent:
            row.append(
                render_percent_with_bar(stats["num_responded"], stats["num_requested"])
            )

        row.append(
            render_percent_with_bar(stats["num_accepted"], stats["num_responded"]),
        )

        table.add_row(*row)

    # Totals
    table.add_section()
    total_row = [
        "[red]Total[/red]",
        str(total_requested),
        str(total_responded),
        str(total_accepted),
    ]
    if show_responded_percent:
        total_row.append(render_percent_with_bar(total_responded, total_requested))

    total_row.append(render_percent_with_bar(total_accepted, total_responded))
    table.add_row(*total_row)
    pprint(table)


def plot_student_stats(regrade_info: RegradeInfoDict, sort_metric: str):
    """
    Plot student statistics using matplotlib/seaborn.

    Contains scoped imports to avoid unnecessary dependencies.
    """
    # pylint: disable=import-outside-toplevel
    import matplotlib.pyplot as plt
    import pandas as pd
    import seaborn as sns

    # pylint: enable=import-outside-toplevel

    sorted_names = _get_sorted_student_names(regrade_info, sort_metric)

    # list of data for plotting; (total_accepted, frac_accepted)
    student_accepted_data: list[tuple[int, float]] = []

    for name in sorted_names:
        student_data = regrade_info[name]
        if student_data["num_responded"] > 0:
            student_accepted_data.append(
                (
                    student_data["num_responded"],
                    student_data["num_accepted"] / student_data["num_responded"],
                )
            )
    df = pd.DataFrame(student_accepted_data, columns=["num_responded", "frac_accepted"])
    sns.jointplot(data=df, x="num_responded", y="frac_accepted", kind="hist")
    plt.show()
