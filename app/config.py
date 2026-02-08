from typing import Optional
from urllib.parse import urlparse

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ALLOWED_JWT_ALGORITHMS = {"HS256", "HS384", "HS512"}


class Settings(BaseSettings):
    # Runtime environment
    environment: str = "development"

    # Core database and auth settings
    database_hostname: str = "localhost"
    database_port: int = 5432
    database_password: str = "password123"
    database_name: str = "fastapi"
    database_username: str = "postgres"
    secret_key: str = "replace-this-in-production"
    algorithm: str = "HS256"
    token_issuer: str = "fastapi-template"
    token_audience: str = "fastapi-template-api"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 30

    # API versioning
    api_latest_version: str = "v1"
    api_supported_versions: list[str] = ["v1"]

    # Optional feature packs (enabled by default)
    enable_optional_rate_limiting: bool = True
    enable_optional_observability: bool = True
    enable_optional_background_jobs: bool = True
    enable_optional_frontend: bool = True

    # Rate limiting / Redis
    redis_url: str = "redis://localhost:6379/0"
    rate_limit_enabled: bool = True
    rate_limit_fail_open: bool = False
    rate_limit_login_limit: int = 10
    rate_limit_login_window_seconds: int = 60
    rate_limit_register_limit: int = 5
    rate_limit_register_window_seconds: int = 60
    rate_limit_read_limit: int = 120
    rate_limit_read_window_seconds: int = 60
    rate_limit_write_limit: int = 60
    rate_limit_write_window_seconds: int = 60

    # Readiness checks
    redis_health_required: bool = False

    # Observability
    metrics_enabled: bool = True
    otel_exporter_otlp_endpoint: Optional[str] = None
    otel_service_name: str = "fastapi-template"
    sentry_dsn: Optional[str] = None
    sentry_environment: str = "development"
    sentry_traces_sample_rate: float = 0.0

    # Outbox/worker reliability controls
    outbox_dispatch_batch_size: int = 100
    outbox_retry_max_attempts: int = 5
    outbox_retry_backoff_seconds: int = 30
    outbox_dispatch_interval_seconds: int = 15

    # OAuth / third-party login
    oauth_state_expire_seconds: int = 300
    oauth_public_base_url: Optional[str] = None
    oauth_frontend_callback_url: str = "/"
    oauth_google_client_id: Optional[str] = None
    oauth_google_client_secret: Optional[str] = None
    oauth_microsoft_client_id: Optional[str] = None
    oauth_microsoft_client_secret: Optional[str] = None
    oauth_apple_client_id: Optional[str] = None
    oauth_apple_client_secret: Optional[str] = None
    oauth_facebook_client_id: Optional[str] = None
    oauth_facebook_client_secret: Optional[str] = None
    oauth_github_client_id: Optional[str] = None
    oauth_github_client_secret: Optional[str] = None

    # Request security controls
    trust_proxy_headers: bool = False
    trusted_hosts: list[str] = ["localhost", "127.0.0.1", "testserver"]
    security_headers_enabled: bool = True
    security_csp_enabled: bool = True
    security_hsts_enabled: bool = False
    security_hsts_max_age_seconds: int = 31_536_000
    security_https_redirect: bool = False

    # CORS
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("algorithm")
    @classmethod
    def validate_algorithm(cls, value: str) -> str:
        normalized = value.strip().upper()
        if normalized not in _ALLOWED_JWT_ALGORITHMS:
            allowed = ", ".join(sorted(_ALLOWED_JWT_ALGORITHMS))
            raise ValueError(f"ALGORITHM must be one of: {allowed}")
        return normalized

    @field_validator("oauth_frontend_callback_url")
    @classmethod
    def validate_oauth_frontend_callback_url(cls, value: str) -> str:
        if not value:
            return "/"
        parsed = urlparse(value)
        if parsed.fragment:
            raise ValueError("OAUTH_FRONTEND_CALLBACK_URL must not include a fragment")
        if parsed.scheme or parsed.netloc:
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError(
                    "OAUTH_FRONTEND_CALLBACK_URL absolute URLs must use http/https"
                )
            return value
        if not value.startswith("/"):
            raise ValueError(
                "OAUTH_FRONTEND_CALLBACK_URL must be an absolute path or absolute URL"
            )
        return value

    @model_validator(mode="after")
    def validate_production_secret(self) -> "Settings":
        if self.environment.lower() in {"prod", "production"}:
            insecure_secrets = {
                "",
                "replace-this-in-production",
                "test-secret-key",
                "changeme",
            }
            if self.secret_key in insecure_secrets or len(self.secret_key) < 32:
                raise ValueError(
                    "SECRET_KEY must be a high-entropy value (>=32 chars) in production"
                )
        return self


settings = Settings()
