from __future__ import annotations

from enum import Enum

from pydantic import AnyHttpUrl, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class MCPAuthMode(str, Enum):
    NONE = "none"
    BEARER = "bearer"


class MCPServerSettings(BaseSettings):
    host: str = "127.0.0.1"
    port: int = 8765
    base_url: AnyHttpUrl = "http://127.0.0.1:8000"
    auth_mode: MCPAuthMode = MCPAuthMode.BEARER
    timeout_seconds: float = 10.0
    allowed_tool_scopes: list[str] = Field(
        default_factory=lambda: ["auth", "users", "posts", "vote"]
    )

    model_config = SettingsConfigDict(
        env_prefix="MCP_SERVER_",
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("timeout_seconds")
    @classmethod
    def validate_timeout(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("MCP_SERVER_TIMEOUT_SECONDS must be > 0")
        return value

    @field_validator("allowed_tool_scopes", mode="before")
    @classmethod
    def parse_scopes(cls, value: object) -> list[str]:
        if isinstance(value, str):
            return [scope.strip() for scope in value.split(",") if scope.strip()]
        if isinstance(value, list):
            return [str(scope).strip() for scope in value if str(scope).strip()]
        raise ValueError("MCP_SERVER_ALLOWED_TOOL_SCOPES must be a list or csv string")


settings = MCPServerSettings()
