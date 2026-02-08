from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .config import settings
from .errors import register_exception_handlers
from .health import readiness_state
from .observability import configure_observability
from .routers import auth, post, user, vote

app = FastAPI()
configure_observability(app)
register_exception_handlers(app)

frontend_dir = Path(__file__).resolve().parent / "frontend"
static_dir = frontend_dir / "static"

if static_dir.exists():
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

if settings.trusted_hosts:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts)

if settings.security_https_redirect:
    app.add_middleware(HTTPSRedirectMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

_DOCS_PATHS = {"/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"}
_CSP_POLICY = (
    "default-src 'self'; "
    "base-uri 'self'; "
    "frame-ancestors 'none'; "
    "object-src 'none'; "
    "form-action 'self'"
)


def _is_auth_path(path: str) -> bool:
    if not path.startswith("/api/"):
        return False
    auth_paths = (
        "/login",
        "/auth/refresh",
        "/auth/logout",
        "/auth/oauth/",
    )
    return any(segment in path for segment in auth_paths)


def _resolve_api_version(path: str, header_version: str | None) -> tuple[str, bool]:
    supported = set(settings.api_supported_versions)
    latest = settings.api_latest_version
    normalized = path.strip("/")
    path_parts = normalized.split("/") if normalized else []

    if len(path_parts) >= 2 and path_parts[0] == "api" and path_parts[1] in supported:
        return path_parts[1], False

    if header_version in supported:
        return str(header_version), False

    return latest, True


@app.middleware("http")
async def api_version_middleware(request: Request, call_next):
    version, defaulted = _resolve_api_version(
        request.url.path, request.headers.get("x-api-version")
    )
    request.state.api_version = version
    response = await call_next(request)
    response.headers["X-API-Version"] = version
    if defaulted:
        response.headers["X-API-Version-Defaulted"] = "true"
    return response


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    if not settings.security_headers_enabled:
        return response

    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault(
        "Permissions-Policy",
        "camera=(), geolocation=(), microphone=(), payment=(), usb=()",
    )
    response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
    response.headers.setdefault("X-Permitted-Cross-Domain-Policies", "none")
    if settings.security_csp_enabled and request.url.path not in _DOCS_PATHS:
        response.headers.setdefault("Content-Security-Policy", _CSP_POLICY)
    if settings.security_hsts_enabled and request.url.scheme == "https":
        response.headers.setdefault(
            "Strict-Transport-Security",
            f"max-age={settings.security_hsts_max_age_seconds}; includeSubDomains",
        )
    if _is_auth_path(request.url.path):
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
    return response


def _include_api_routers() -> None:
    latest_prefix = f"/api/{settings.api_latest_version}"
    if settings.api_latest_version not in settings.api_supported_versions:
        raise RuntimeError("api_latest_version must be included in api_supported_versions")

    routers = [post.router, user.router, auth.router, vote.router]
    for router in routers:
        app.include_router(router, prefix=latest_prefix)


_include_api_routers()


@app.get("/", include_in_schema=False)
def root():
    if settings.enable_optional_frontend:
        index_file = frontend_dir / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
    return {"message": "FastAPI template API is running"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready():
    is_ready, checks = readiness_state()
    if not is_ready:
        raise HTTPException(
            status_code=503,
            detail={
                "detail": "Service dependencies are not ready",
                "error_code": "service_not_ready",
            },
        )
    return {"status": "ok", "checks": checks}
