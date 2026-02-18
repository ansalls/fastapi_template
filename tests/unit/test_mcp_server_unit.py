from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from app.domains.mcp_server.client import APIClient
from app.domains.mcp_server.config import MCPServerSettings
from app.domains.mcp_server.problem import APIClientError, ProblemDocument
from app.domains.mcp_server.server import MCPServer, create_mcp_app
from app.domains.mcp_server.tools import build_resources, build_tool_registry


def test_mcp_server_settings_parse_csv_scopes():
    settings = MCPServerSettings(allowed_tool_scopes="auth, users")
    assert settings.allowed_tool_scopes == ["auth", "users"]


def test_mcp_server_list_tools_filters_by_scope():
    settings = MCPServerSettings(allowed_tool_scopes=["auth"])
    server = MCPServer(settings)
    tools = server.list_tools()
    assert {tool.scope for tool in tools} == {"auth"}
    asyncio.run(server.close())


def test_tool_registry_contains_api_v1_anchors():
    registry = build_tool_registry()
    assert registry["auth"][0].path.startswith("/api/v1")
    assert registry["users"][0].path.startswith("/api/v1")


def test_resources_include_openapi_and_health():
    resources = build_resources()
    assert {resource.name for resource in resources} == {"openapi", "health"}


def test_create_mcp_app_has_core_endpoints():
    app = create_mcp_app(MCPServerSettings(allowed_tool_scopes=["auth"]))
    client = TestClient(app)

    tools_response = client.get("/mcp/tools")
    config_response = client.get("/mcp/config")

    assert tools_response.status_code == 200
    assert config_response.status_code == 200
    assert config_response.json()["allowed_tool_scopes"] == ["auth"]


def test_call_tool_returns_problem_when_tool_missing():
    settings = MCPServerSettings(allowed_tool_scopes=["auth"])
    server = MCPServer(settings)

    result = asyncio.run(server.call_tool(tool_name="users.list", args={}))

    assert result.ok is False
    assert result.problem is not None
    assert result.problem.error_code == "mcp_tool_not_found"
    assert result.action_id
    assert result.session_id
    asyncio.run(server.close())


def test_call_tool_surfaces_normalized_problem(monkeypatch):
    settings = MCPServerSettings(allowed_tool_scopes=["auth"])
    server = MCPServer(settings)

    async def _raise_error(*args, **kwargs):
        raise APIClientError(
            ProblemDocument(
                title="Unauthorized",
                status=401,
                detail="Invalid token",
                instance="/api/v1/login",
                error_code="auth_invalid",
            )
        )

    monkeypatch.setattr(APIClient, "request", _raise_error)
    result = asyncio.run(
        server.call_tool(
            tool_name="auth.login",
            args={"body": {}, "session_id": "session-123", "source": "test-suite"},
        )
    )

    assert result.ok is False
    assert result.problem is not None
    assert result.problem.status == 401
    assert result.session_id == "session-123"
    assert result.action_id
    asyncio.run(server.close())
