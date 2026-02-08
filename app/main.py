from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

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

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


def _include_api_routers() -> None:
    latest_prefix = f"/api/{settings.api_latest_version}"
    if settings.api_latest_version not in settings.api_supported_versions:
        raise RuntimeError("api_latest_version must be included in api_supported_versions")

    routers = [post.router, user.router, auth.router, vote.router]
    for router in routers:
        app.include_router(router, prefix=latest_prefix)
    for router in routers:
        # Unversioned /api routes default to latest for convenience.
        app.include_router(router, prefix="/api", include_in_schema=False)
    for router in routers:
        # Legacy unversioned routes stay available for backwards compatibility.
        app.include_router(router)


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
