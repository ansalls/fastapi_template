import runpy
import warnings
from pathlib import Path

import pytest
from app import main
from fastapi.testclient import TestClient

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


def test_include_api_routers_rejects_invalid_latest_version(monkeypatch):
    monkeypatch.setattr(main.settings, "api_latest_version", "v9")
    monkeypatch.setattr(main.settings, "api_supported_versions", ["v1"])
    with pytest.raises(RuntimeError):
        main._include_api_routers()
    monkeypatch.setattr(main.settings, "api_latest_version", "v1")
    monkeypatch.setattr(main.settings, "api_supported_versions", ["v1"])


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
