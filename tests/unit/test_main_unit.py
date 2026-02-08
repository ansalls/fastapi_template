import runpy
import warnings
from pathlib import Path
from types import SimpleNamespace

import pytest
from app import main
from fastapi import APIRouter
from fastapi.testclient import TestClient
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware

pytestmark = pytest.mark.unit


def test_root_serves_frontend_html():
    client = TestClient(main.app)
    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Template Control Panel" in response.text


def test_root_returns_fallback_when_index_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "frontend_dir", tmp_path)

    response = main.root()

    assert response == {"message": "FastAPI template API is running"}


def test_root_returns_fallback_when_frontend_is_disabled(monkeypatch):
    monkeypatch.setattr(main.settings, "enable_optional_frontend", False)
    assert main.root() == {"message": "FastAPI template API is running"}
    monkeypatch.setattr(main.settings, "enable_optional_frontend", True)


def test_health_endpoint_returns_ok():
    client = TestClient(main.app)
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_endpoint_success_and_failure(monkeypatch):
    client = TestClient(main.app, raise_server_exceptions=False)

    monkeypatch.setattr(main, "readiness_state", lambda: (True, {"database": True, "redis": True}))
    success = client.get("/ready")
    assert success.status_code == 200
    assert success.json()["checks"]["database"] is True

    monkeypatch.setattr(main, "readiness_state", lambda: (False, {"database": False, "redis": True}))
    failed = client.get("/ready")
    assert failed.status_code == 503
    assert failed.json()["error_code"] == "service_not_ready"


def test_api_version_resolution_and_headers():
    assert main._resolve_api_version("/api/v1/posts", None) == ("v1", False)
    assert main._resolve_api_version("/health", "v1") == ("v1", False)
    assert main._resolve_api_version("/health", "v999") == ("v1", True)

    client = TestClient(main.app)
    defaulted = client.get("/health")
    assert defaulted.headers["X-API-Version"] == "v1"
    assert defaulted.headers["X-API-Version-Defaulted"] == "true"

    explicit = client.get("/health", headers={"x-api-version": "v1"})
    assert explicit.headers["X-API-Version"] == "v1"
    assert "X-API-Version-Defaulted" not in explicit.headers


def test_security_headers_can_be_disabled(monkeypatch):
    monkeypatch.setattr(main.settings, "security_headers_enabled", False)
    client = TestClient(main.app)
    response = client.get("/health")
    assert response.status_code == 200
    assert "x-content-type-options" not in response.headers
    monkeypatch.setattr(main.settings, "security_headers_enabled", True)


def test_security_headers_include_hsts_for_https(monkeypatch):
    monkeypatch.setattr(main.settings, "security_hsts_enabled", True)
    client = TestClient(main.app, base_url="https://testserver")
    response = client.get("/health")
    assert response.status_code == 200
    assert response.headers["strict-transport-security"].startswith("max-age=")
    monkeypatch.setattr(main.settings, "security_hsts_enabled", False)


def test_include_api_routers_rejects_invalid_latest_version(monkeypatch):
    monkeypatch.setattr(main.settings, "api_latest_version", "v9")
    monkeypatch.setattr(main.settings, "api_supported_versions", ["v1"])
    with pytest.raises(RuntimeError):
        main._include_api_routers()
    monkeypatch.setattr(main.settings, "api_latest_version", "v1")
    monkeypatch.setattr(main.settings, "api_supported_versions", ["v1"])


def test_discover_domain_routers_returns_empty_when_package_missing(monkeypatch):
    package_name = "app.missing_domains"

    def fake_import(module_path: str):
        exc = ModuleNotFoundError(module_path)
        exc.name = module_path
        raise exc

    monkeypatch.setattr(main, "import_module", fake_import)
    assert main._discover_domain_routers(package_name) == []


def test_discover_domain_routers_reraises_unrelated_import_error(monkeypatch):
    package_name = "app.domains"

    def fake_import(module_path: str):
        exc = ModuleNotFoundError("redis")
        exc.name = "redis"
        raise exc

    monkeypatch.setattr(main, "import_module", fake_import)
    with pytest.raises(ModuleNotFoundError):
        main._discover_domain_routers(package_name)


def test_discover_domain_routers_returns_empty_for_non_package(monkeypatch):
    monkeypatch.setattr(main, "import_module", lambda _module_path: object())
    assert main._discover_domain_routers("app.domains") == []


def test_discover_domain_routers_collects_sorted_package_routers(monkeypatch):
    package = SimpleNamespace(__path__=["/tmp/domains"])
    expected_alpha = APIRouter(prefix="/alpha")
    expected_zeta = APIRouter(prefix="/zeta")

    monkeypatch.setattr(main, "import_module", lambda _module_path: package)
    monkeypatch.setattr(
        main,
        "iter_modules",
        lambda _paths: [
            SimpleNamespace(name="zeta", ispkg=True),
            SimpleNamespace(name="ignore_file", ispkg=False),
            SimpleNamespace(name="alpha", ispkg=True),
        ],
    )
    monkeypatch.setattr(
        main,
        "_load_optional_domain_router",
        lambda module_path: {
            "app.domains.alpha.router": expected_alpha,
            "app.domains.zeta.router": expected_zeta,
        }.get(module_path),
    )
    routers = main._discover_domain_routers("app.domains")
    assert routers == [expected_alpha, expected_zeta]


def test_discover_domain_routers_skips_packages_without_router(monkeypatch):
    package = SimpleNamespace(__path__=["/tmp/domains"])
    expected_alpha = APIRouter(prefix="/alpha")

    monkeypatch.setattr(main, "import_module", lambda _module_path: package)
    monkeypatch.setattr(
        main,
        "iter_modules",
        lambda _paths: [
            SimpleNamespace(name="alpha", ispkg=True),
            SimpleNamespace(name="beta", ispkg=True),
        ],
    )
    monkeypatch.setattr(
        main,
        "_load_optional_domain_router",
        lambda module_path: expected_alpha
        if module_path == "app.domains.alpha.router"
        else None,
    )
    routers = main._discover_domain_routers("app.domains")
    assert routers == [expected_alpha]


def test_load_optional_domain_router_returns_none_when_router_module_missing(monkeypatch):
    module_path = "app.domains.billing.router"

    def fake_import(_module_path: str):
        exc = ModuleNotFoundError(module_path)
        exc.name = module_path
        raise exc

    monkeypatch.setattr(main, "import_module", fake_import)
    assert main._load_optional_domain_router(module_path) is None


def test_load_optional_domain_router_reraises_unrelated_import_error(monkeypatch):
    module_path = "app.domains.billing.router"

    def fake_import(_module_path: str):
        exc = ModuleNotFoundError("dependency")
        exc.name = "dependency"
        raise exc

    monkeypatch.setattr(main, "import_module", fake_import)
    with pytest.raises(ModuleNotFoundError):
        main._load_optional_domain_router(module_path)


def test_load_optional_domain_router_returns_router_instance(monkeypatch):
    router = APIRouter(prefix="/billing")
    monkeypatch.setattr(main, "import_module", lambda _module_path: SimpleNamespace(router=router))
    assert main._load_optional_domain_router("app.domains.billing.router") is router


def test_load_optional_domain_router_returns_none_for_non_router_attribute(monkeypatch):
    monkeypatch.setattr(main, "import_module", lambda _module_path: SimpleNamespace(router="not-router"))
    assert main._load_optional_domain_router("app.domains.billing.router") is None


def test_main_module_adds_https_redirect_middleware_when_enabled(monkeypatch):
    monkeypatch.setattr(main.settings, "trusted_hosts", [])
    monkeypatch.setattr(main.settings, "security_https_redirect", True)

    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            category=RuntimeWarning,
            message=".*app.main.*found in sys.modules.*",
        )
        module_vars = runpy.run_module(
            "app.main", run_name="__coverage_main_https_redirect"
        )

    middleware_classes = [entry.cls for entry in module_vars["app"].user_middleware]
    assert HTTPSRedirectMiddleware in middleware_classes

    monkeypatch.setattr(main.settings, "trusted_hosts", ["localhost", "127.0.0.1", "testserver"])
    monkeypatch.setattr(main.settings, "security_https_redirect", False)


def test_main_module_handles_missing_static_dir(monkeypatch):
    original_exists = Path.exists

    def fake_exists(self):
        if self.as_posix().endswith("app/frontend/static"):
            return False
        return original_exists(self)

    monkeypatch.setattr(Path, "exists", fake_exists)

    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            category=RuntimeWarning,
            message=".*app.main.*found in sys.modules.*",
        )
        module_vars = runpy.run_module("app.main", run_name="__coverage_main_no_static")
    mounted_static = [
        route
        for route in module_vars["app"].routes
        if getattr(route, "name", "") == "static"
    ]

    assert mounted_static == []
