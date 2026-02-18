from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ToolScope(str, Enum):
    AUTH = "auth"
    USERS = "users"
    POSTS = "posts"
    VOTE = "vote"


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    scope: ToolScope
    method: str
    path: str


@dataclass(frozen=True)
class ResourceDefinition:
    uri: str
    name: str
    description: str


def build_tool_registry() -> dict[str, list[ToolDefinition]]:
    """Grouped registry, anchored to /api/v1 and existing router tags."""
    return {
        ToolScope.AUTH.value: [
            ToolDefinition(
                name="auth.login",
                description="Authentication: exchange username/password for token pair.",
                scope=ToolScope.AUTH,
                method="POST",
                path="/api/v1/login",
            ),
            ToolDefinition(
                name="auth.providers",
                description="Authentication: list configured OAuth providers.",
                scope=ToolScope.AUTH,
                method="GET",
                path="/api/v1/auth/oauth/providers",
            ),
        ],
        ToolScope.USERS.value: [
            ToolDefinition(
                name="users.list",
                description="Users: list users from /api/v1/users endpoint.",
                scope=ToolScope.USERS,
                method="GET",
                path="/api/v1/users",
            ),
            ToolDefinition(
                name="users.get",
                description="Users: fetch a user by id from /api/v1/users/{user_id}.",
                scope=ToolScope.USERS,
                method="GET",
                path="/api/v1/users/{user_id}",
            ),
        ],
        ToolScope.POSTS.value: [
            ToolDefinition(
                name="posts.list",
                description="Posts: list posts using /api/v1/posts.",
                scope=ToolScope.POSTS,
                method="GET",
                path="/api/v1/posts",
            ),
            ToolDefinition(
                name="posts.get",
                description="Posts: fetch a post by id using /api/v1/posts/{post_id}.",
                scope=ToolScope.POSTS,
                method="GET",
                path="/api/v1/posts/{post_id}",
            ),
        ],
        ToolScope.VOTE.value: [
            ToolDefinition(
                name="vote.create",
                description="Vote: submit up/down vote through /api/v1/vote.",
                scope=ToolScope.VOTE,
                method="POST",
                path="/api/v1/vote/",
            )
        ],
    }


def build_resources() -> list[ResourceDefinition]:
    return [
        ResourceDefinition(
            uri="resource://fastapi/openapi",
            name="openapi",
            description="OpenAPI schema at /openapi.json.",
        ),
        ResourceDefinition(
            uri="resource://fastapi/health",
            name="health",
            description="Health check summary from /health.",
        ),
    ]
