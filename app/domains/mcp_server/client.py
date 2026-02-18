from __future__ import annotations

import logging
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel

from .problem import APIClientError, ProblemDocument, normalized_problem

ResponseModelT = TypeVar("ResponseModelT", bound=BaseModel)
logger = logging.getLogger(__name__)


class APIClient:
    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float,
        bearer_token: str | None = None,
    ) -> None:
        headers: dict[str, str] = {}
        if bearer_token:
            headers["Authorization"] = f"Bearer {bearer_token}"
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout_seconds,
            headers=headers,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def request(
        self,
        *,
        method: str,
        path: str,
        response_model: type[ResponseModelT],
        json_body: BaseModel | dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        action_id: str | None = None,
        session_id: str | None = None,
    ) -> ResponseModelT:
        payload = json_body.model_dump() if isinstance(json_body, BaseModel) else json_body
        logger.info(
            "mcp_outbound_request",
            extra={
                "action_id": action_id,
                "session_id": session_id,
                "method": method,
                "path": path,
            },
        )
        response = await self._client.request(
            method=method,
            url=path,
            json=payload,
            params=params,
            headers={
                "X-MCP-Action-ID": action_id or "",
                "X-MCP-Session-ID": session_id or "",
            },
        )
        if response.is_error:
            self._raise_api_error(
                path=path,
                response=response,
                action_id=action_id,
                session_id=session_id,
            )
        logger.info(
            "mcp_outbound_response",
            extra={
                "action_id": action_id,
                "session_id": session_id,
                "status_code": response.status_code,
                "path": path,
            },
        )
        return response_model.model_validate(response.json())

    @staticmethod
    def _raise_api_error(
        *,
        path: str,
        response: httpx.Response,
        action_id: str | None = None,
        session_id: str | None = None,
    ) -> None:
        data = response.json() if response.content else {}
        if isinstance(data, dict) and all(
            key in data for key in ("title", "status", "detail", "error_code")
        ):
            problem = ProblemDocument.model_validate(data)
        else:
            detail = str(data.get("detail", response.text or "Request failed")) if isinstance(data, dict) else (
                response.text or "Request failed"
            )
            problem = normalized_problem(
                status=response.status_code,
                detail=detail,
                instance=path,
                error_code="request_failed",
            )
        logger.warning(
            "mcp_outbound_error",
            extra={
                "action_id": action_id,
                "session_id": session_id,
                "status": problem.status,
                "error_code": problem.error_code,
                "instance": problem.instance,
            },
        )
        raise APIClientError(problem)
