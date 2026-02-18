from __future__ import annotations

from collections.abc import Iterable
from contextlib import asynccontextmanager
import logging
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request
from pydantic import BaseModel, ConfigDict, Field

from .client import APIClient
from .config import MCPAuthMode, MCPServerSettings
from .problem import APIClientError, ProblemDocument
from .tools import ResourceDefinition, build_resources, build_tool_registry

logger = logging.getLogger(__name__)


class ToolCallRequest(BaseModel):
    tool_name: str
    args: dict[str, Any] = Field(default_factory=dict)
    session_id: str | None = None
    source: str | None = None


class ToolCallResponse(BaseModel):
    ok: bool
    data: dict[str, Any] | list[dict[str, Any]] | None = None
    problem: ProblemDocument | None = None
    action_id: str
    session_id: str


class MCPTool(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    description: str
    scope: str
    method: str
    path: str


class MCPResource(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uri: str
    name: str
    description: str


class MCPServer:
    def __init__(self, settings: MCPServerSettings) -> None:
        registry = build_tool_registry()
        self._allowed_scopes = set(settings.allowed_tool_scopes)
        self._tools = {
            tool.name: tool
            for scope, tools in registry.items()
            if scope in self._allowed_scopes
            for tool in tools
        }
        self._resources = build_resources()
        self._client = APIClient(
            base_url=str(settings.base_url),
            timeout_seconds=settings.timeout_seconds,
        )

    def list_tools(self) -> list[MCPTool]:
        return [
            MCPTool(
                name=tool.name,
                description=tool.description,
                scope=tool.scope.value,
                method=tool.method,
                path=tool.path,
            )
            for tool in self._tools.values()
        ]

    def list_resources(self) -> list[MCPResource]:
        return [MCPResource.model_validate(resource) for resource in self._resources]

    async def close(self) -> None:
        await self._client.close()

    async def call_tool(self, *, tool_name: str, args: dict[str, Any]) -> ToolCallResponse:
        action_id = str(uuid4())
        session_id = str(args.pop("session_id", "") or uuid4())
        source = str(args.pop("source", "unknown"))
        logger.info(
            "mcp_tool_invocation_started",
            extra={
                "action_id": action_id,
                "session_id": session_id,
                "tool_name": tool_name,
                "source": source,
            },
        )
        tool = self._tools.get(tool_name)
        if not tool:
            logger.warning(
                "mcp_tool_not_found",
                extra={
                    "action_id": action_id,
                    "session_id": session_id,
                    "tool_name": tool_name,
                    "source": source,
                },
            )
            return ToolCallResponse(
                ok=False,
                problem=ProblemDocument(
                    title="Not Found",
                    status=404,
                    detail=f"Tool '{tool_name}' is not registered",
                    instance=f"tool:{tool_name}",
                    error_code="mcp_tool_not_found",
                ),
                action_id=action_id,
                session_id=session_id,
            )

        try:
            path = tool.path.format(**args)
        except KeyError as exc:
            logger.warning(
                "mcp_tool_missing_argument",
                extra={
                    "action_id": action_id,
                    "session_id": session_id,
                    "tool_name": tool_name,
                    "source": source,
                    "argument": exc.args[0],
                },
            )
            return ToolCallResponse(
                ok=False,
                problem=ProblemDocument(
                    title="Bad Request",
                    status=400,
                    detail=f"Missing tool argument: {exc.args[0]}",
                    instance=f"tool:{tool_name}",
                    error_code="mcp_missing_argument",
                ),
                action_id=action_id,
                session_id=session_id,
            )

        query = args.get("query") if isinstance(args.get("query"), dict) else None
        body = args.get("body") if isinstance(args.get("body"), dict) else None

        try:
            result = await self._client.request(
                method=tool.method,
                path=path,
                params=query,
                json_body=body,
                response_model=FreeFormResponse,
                action_id=action_id,
                session_id=session_id,
            )
            logger.info(
                "mcp_tool_invocation_succeeded",
                extra={
                    "action_id": action_id,
                    "session_id": session_id,
                    "tool_name": tool_name,
                    "source": source,
                },
            )
            return ToolCallResponse(
                ok=True,
                data=result.data,
                action_id=action_id,
                session_id=session_id,
            )
        except APIClientError as exc:
            logger.warning(
                "mcp_tool_invocation_failed",
                extra={
                    "action_id": action_id,
                    "session_id": session_id,
                    "tool_name": tool_name,
                    "source": source,
                    "error_code": exc.problem.error_code,
                    "status": exc.problem.status,
                },
            )
            return ToolCallResponse(
                ok=False,
                problem=exc.problem,
                action_id=action_id,
                session_id=session_id,
            )


class FreeFormResponse(BaseModel):
    data: dict[str, Any] | list[dict[str, Any]] | None = None

    @classmethod
    def model_validate(cls, obj: Any, *args: Any, **kwargs: Any) -> "FreeFormResponse":
        return super().model_validate({"data": obj}, *args, **kwargs)


def _serialize_tools(server: MCPServer) -> list[dict[str, Any]]:
    return [tool.model_dump() for tool in server.list_tools()]


def _serialize_resources(resources: Iterable[ResourceDefinition]) -> list[dict[str, Any]]:
    return [MCPResource.model_validate(resource).model_dump() for resource in resources]


def create_mcp_app(settings: MCPServerSettings | None = None) -> FastAPI:
    cfg = settings or MCPServerSettings()
    mcp_server = MCPServer(cfg)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        await mcp_server.close()

    app = FastAPI(title="fastapi-template-mcp", lifespan=lifespan)

    @app.get("/mcp/tools")
    async def list_tools(request: Request) -> list[dict[str, Any]]:
        logger.info(
            "mcp_tools_listed",
            extra={
                "source_ip": request.client.host if request.client else "unknown",
                "path": request.url.path,
            },
        )
        return _serialize_tools(mcp_server)

    @app.get("/mcp/resources")
    async def list_resources(request: Request) -> list[dict[str, Any]]:
        logger.info(
            "mcp_resources_listed",
            extra={
                "source_ip": request.client.host if request.client else "unknown",
                "path": request.url.path,
            },
        )
        return [resource.model_dump() for resource in mcp_server.list_resources()]

    @app.post("/mcp/tools/call", response_model=ToolCallResponse)
    async def call_tool(payload: ToolCallRequest, request: Request) -> ToolCallResponse:
        args = {
            **payload.args,
            "session_id": payload.session_id,
            "source": payload.source or (request.client.host if request.client else "unknown"),
        }
        return await mcp_server.call_tool(tool_name=payload.tool_name, args=args)

    @app.get("/mcp/config")
    async def show_config() -> dict[str, Any]:
        auth_required = cfg.auth_mode == MCPAuthMode.BEARER
        return {
            "base_url": str(cfg.base_url),
            "auth_mode": cfg.auth_mode.value,
            "auth_required": auth_required,
            "timeout_seconds": cfg.timeout_seconds,
            "allowed_tool_scopes": sorted(cfg.allowed_tool_scopes),
        }

    @app.get("/mcp/health")
    async def mcp_health() -> dict[str, str]:
        return {"status": "ok"}

    return app
