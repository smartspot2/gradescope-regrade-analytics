from dataclasses import dataclass
from datetime import datetime
from typing import Literal, NotRequired, Optional, TypedDict


class RegradeRequest(TypedDict):
    """
    Type for a regrade request, either made by a student or as a response by staff.
    """

    user: Literal["student"] | Literal["staff"]
    text: str

    timestamp: float
    """POSIX timestamp for the regrade request"""

    accepted: NotRequired[bool]


class ReviewData(TypedDict):
    """
    Regrade request review data; contains information fetched from the regrade page.
    """

    link: str
    reviews: list[RegradeRequest]

    accepted: Optional[bool]

    score: float
    weight: float

type LinkMap = dict[str, ReviewData]

class RegradeInfoMetadata(TypedDict):
    """
    Regrade request metadata; initially only contains information fetched from the summary request table.
    Later on, this is updated with information fetched from the submission.
    """

    question: str
    question_link: str
    grader: str
    review_link: str

class RegradeInfo(TypedDict):
    """
    Regrade request information; contains information fetched from the summary request table
    """

    # total number of requests that were submtited by the student,
    # including when multiple comments are submitted for a single question
    num_comments: int

    # list of questions that the student submitted a regrade request for,
    # along with other metadata for each question
    regrades: list[RegradeInfoMetadata]

    # summary information for the student
    num_accepted: int
    num_responded: int


type RegradeInfoDict = dict[str, RegradeInfo]
"""
Map from a student's name to all of the regrade requests submitted by the student.
"""

class StaffRegradeStatistics(TypedDict):
    """Statistics for staff"""
    num_requested: int
    num_responded: int
    num_accepted: int


@dataclass
class PrintOptions:
    """
    Collection of options for final printing.
    """

    requests: bool
    """Print all regrade request details."""

    student_stats: bool
    """Print regrade request statistics for each student."""

    plot_student_stats: bool
    """Plot regrade request statistics for each student."""

    staff_stats: bool
    """Print regrade request statistics for each staff member."""

    @classmethod
    def default(cls):
        """Default print options."""
        return cls(
            requests=True,
            student_stats=True,
            plot_student_stats=False,
            staff_stats=True,
        )
