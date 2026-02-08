from pathlib import Path
import runpy
import warnings

from fastapi.testclient import TestClient

from app import main


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


def test_health_endpoint_returns_ok():
    client = TestClient(main.app)
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


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
        route for route in module_vars["app"].routes if getattr(route, "name", "") == "static"
    ]

    assert mounted_static == []
