from __future__ import annotations

import pytest
from httpx import Request, Response

from app.domains.mcp_server.client import APIClient
from app.domains.mcp_server.problem import APIClientError

pytestmark = pytest.mark.unit


def test_raise_api_error_uses_problem_document_payload():
    response = Response(
        400,
        json={
            "title": "Bad Request",
            "status": 400,
            "detail": "broken",
            "instance": "/api/v1/users",
            "error_code": "bad_request",
        },
        request=Request("GET", "http://testserver/api/v1/users"),
    )

    with pytest.raises(APIClientError) as exc_info:
        APIClient._raise_api_error(path="/api/v1/users", response=response)

    assert exc_info.value.problem.error_code == "bad_request"


def test_raise_api_error_normalizes_non_problem_payload():
    response = Response(
        500,
        json={"detail": "boom"},
        request=Request("GET", "http://testserver/api/v1/users"),
    )

    with pytest.raises(APIClientError) as exc_info:
        APIClient._raise_api_error(path="/api/v1/users", response=response)

    assert exc_info.value.problem.error_code == "request_failed"
    assert exc_info.value.problem.status == 500
