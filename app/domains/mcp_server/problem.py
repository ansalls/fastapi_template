from __future__ import annotations

from http import HTTPStatus

from pydantic import BaseModel


class ProblemDocument(BaseModel):
    type: str = "about:blank"
    title: str
    status: int
    detail: str
    instance: str = ""
    error_code: str = "request_failed"


class APIClientError(Exception):
    def __init__(self, problem: ProblemDocument):
        self.problem = problem
        super().__init__(problem.detail)


def normalized_problem(*, status: int, detail: str, instance: str, error_code: str) -> ProblemDocument:
    try:
        title = HTTPStatus(status).phrase
    except ValueError:
        title = "Error"
    return ProblemDocument(
        title=title,
        status=status,
        detail=detail,
        instance=instance,
        error_code=error_code,
    )
