import pytest
from app import errors
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

pytestmark = pytest.mark.unit


def _request(path: str = "/problem") -> Request:
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "path": path,
        "raw_path": path.encode("utf-8"),
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "scheme": "http",
        "root_path": "",
    }
    return Request(scope)


def test_status_helpers_and_normalize_detail():
    assert errors._status_title(200) == "OK"
    assert errors._status_title(999) == "Error"
    assert errors._status_error_code(503) == "http_503"
    assert errors._normalize_detail({"detail": "x", "error_code": "custom"}) == (
        "x",
        "custom",
    )
    assert errors._normalize_detail(None) == ("Request failed", "request_failed")
    assert errors._normalize_detail("plain") == ("plain", "request_failed")


def test_problem_document_and_response_include_expected_fields():
    request = _request("/hello")
    document = errors.problem_document(
        request=request,
        status_code=418,
        title="Teapot",
        detail="short and stout",
        error_code="teapot",
        extra={"meta": "yes"},
    )
    assert document["instance"] == "/hello"
    assert document["meta"] == "yes"

    response = errors.problem_response(
        request=request,
        status_code=429,
        title="Too Many Requests",
        detail="Slow down",
        error_code="rate_limit_exceeded",
        headers={"Retry-After": "10"},
    )
    assert response.status_code == 429
    assert response.media_type == "application/problem+json"
    assert response.headers["Retry-After"] == "10"


def test_registered_handlers_return_problem_details():
    app = FastAPI()
    errors.register_exception_handlers(app)

    @app.get("/http")
    def _http_error():
        raise HTTPException(
            status_code=409, detail={"detail": "conflict", "error_code": "conflict"}
        )

    @app.get("/validation")
    def _validation_error(limit: int):
        return {"limit": limit}

    @app.get("/boom")
    def _boom():
        raise RuntimeError("unexpected")

    client = TestClient(app, raise_server_exceptions=False)

    http_response = client.get("/http")
    assert http_response.status_code == 409
    assert http_response.headers["content-type"].startswith("application/problem+json")
    assert http_response.json()["error_code"] == "conflict"

    validation_response = client.get("/validation?limit=oops")
    assert validation_response.status_code == 422
    payload = validation_response.json()
    assert payload["error_code"] == "validation_error"
    assert payload["errors"]

    boom_response = client.get("/boom")
    assert boom_response.status_code == 500
    assert boom_response.json()["error_code"] == "http_500"
