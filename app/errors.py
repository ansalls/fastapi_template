from __future__ import annotations

from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


def _status_title(status_code: int) -> str:
    try:
        return HTTPStatus(status_code).phrase
    except ValueError:
        return "Error"


def _status_error_code(status_code: int) -> str:
    return f"http_{status_code}"


def _normalize_detail(detail: Any) -> tuple[str, str]:
    if isinstance(detail, dict):
        text = str(detail.get("detail", "Request failed"))
        code = str(detail.get("error_code", "request_failed"))
        return text, code
    if detail is None:
        return "Request failed", "request_failed"
    return str(detail), "request_failed"


def problem_document(
    *,
    request: Request,
    status_code: int,
    title: str,
    detail: str,
    error_code: str,
    type_uri: str = "about:blank",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "type": type_uri,
        "title": title,
        "status": status_code,
        "detail": detail,
        "instance": str(request.url.path),
        "error_code": error_code,
    }
    if extra:
        payload.update(extra)
    return payload


def problem_response(
    *,
    request: Request,
    status_code: int,
    title: str,
    detail: str,
    error_code: str,
    type_uri: str = "about:blank",
    headers: dict[str, str] | None = None,
    extra: dict[str, Any] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=problem_document(
            request=request,
            status_code=status_code,
            title=title,
            detail=detail,
            error_code=error_code,
            type_uri=type_uri,
            extra=extra,
        ),
        headers=headers,
        media_type="application/problem+json",
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    @app.exception_handler(StarletteHTTPException)
    async def _http_exception_handler(
        request: Request, exc: HTTPException | StarletteHTTPException
    ) -> JSONResponse:
        detail, error_code = _normalize_detail(exc.detail)
        return problem_response(
            request=request,
            status_code=exc.status_code,
            title=_status_title(exc.status_code),
            detail=detail,
            error_code=error_code or _status_error_code(exc.status_code),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return problem_response(
            request=request,
            status_code=422,
            title=_status_title(422),
            detail="Request validation failed",
            error_code="validation_error",
            extra={"errors": exc.errors()},
        )

    @app.exception_handler(Exception)
    async def _unhandled_exception_handler(
        request: Request, _: Exception
    ) -> JSONResponse:
        return problem_response(
            request=request,
            status_code=500,
            title=_status_title(500),
            detail="Internal Server Error",
            error_code=_status_error_code(500),
        )
