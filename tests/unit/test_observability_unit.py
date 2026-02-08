import builtins
import logging

import pytest
from app import observability
from fastapi import FastAPI

pytestmark = pytest.mark.unit


def _patch_import_error(monkeypatch, module_prefix: str):
    real_import = builtins.__import__

    def _fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name.startswith(module_prefix):
            raise ImportError(f"blocked import for {name}")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _fake_import)


def test_configure_structured_logging_success_and_idempotent(monkeypatch):
    root = logging.getLogger()
    if hasattr(root, "_json_logging_configured"):
        delattr(root, "_json_logging_configured")

    assert observability.configure_structured_logging() is True
    assert observability.configure_structured_logging() is False

    delattr(root, "_json_logging_configured")
    _patch_import_error(monkeypatch, "pythonjsonlogger")
    assert observability.configure_structured_logging() is True


def test_configure_metrics_paths(monkeypatch):
    app = FastAPI()
    monkeypatch.setattr(observability.settings, "enable_optional_observability", False)
    assert observability.configure_metrics(app) is False

    monkeypatch.setattr(observability.settings, "enable_optional_observability", True)
    monkeypatch.setattr(observability.settings, "metrics_enabled", True)
    app_with_metrics = FastAPI()
    app_with_metrics.add_api_route("/metrics", lambda: {"ok": True}, methods=["GET"])
    assert observability.configure_metrics(app_with_metrics) is False

    import_error_app = FastAPI()
    _patch_import_error(monkeypatch, "prometheus_fastapi_instrumentator")
    assert observability.configure_metrics(import_error_app) is False


def test_configure_metrics_success(monkeypatch):
    monkeypatch.setattr(observability.settings, "enable_optional_observability", True)
    monkeypatch.setattr(observability.settings, "metrics_enabled", True)
    app = FastAPI()
    assert observability.configure_metrics(app) is True
    assert observability._route_exists(app, "/metrics") is True


def test_configure_tracing_paths(monkeypatch):
    app = FastAPI()
    monkeypatch.setattr(observability.settings, "enable_optional_observability", True)
    monkeypatch.setattr(observability.settings, "otel_exporter_otlp_endpoint", None)
    assert observability.configure_tracing(app) is False

    monkeypatch.setattr(
        observability.settings,
        "otel_exporter_otlp_endpoint",
        "http://localhost:4318/v1/traces",
    )
    app.state.otel_configured = True
    assert observability.configure_tracing(app) is False


def test_configure_tracing_import_error(monkeypatch):
    monkeypatch.setattr(observability.settings, "enable_optional_observability", True)
    monkeypatch.setattr(
        observability.settings,
        "otel_exporter_otlp_endpoint",
        "http://localhost:4318/v1/traces",
    )
    app = FastAPI()
    _patch_import_error(monkeypatch, "opentelemetry")
    assert observability.configure_tracing(app) is False


def test_configure_tracing_success(monkeypatch):
    monkeypatch.setattr(observability.settings, "enable_optional_observability", True)
    monkeypatch.setattr(
        observability.settings,
        "otel_exporter_otlp_endpoint",
        "http://localhost:4318/v1/traces",
    )
    monkeypatch.setattr(observability.settings, "otel_service_name", "test-service")
    app = FastAPI()
    assert observability.configure_tracing(app) is True
    assert app.state.otel_configured is True


def test_configure_sentry_paths(monkeypatch):
    monkeypatch.setattr(observability.settings, "enable_optional_observability", True)
    monkeypatch.setattr(observability.settings, "sentry_dsn", None)
    assert observability.configure_sentry() is False

    monkeypatch.setattr(observability.settings, "sentry_dsn", "https://x@y.ingest.sentry.io/1")
    _patch_import_error(monkeypatch, "sentry_sdk")
    assert observability.configure_sentry() is False


def test_configure_sentry_success_and_existing_client(monkeypatch):
    import sentry_sdk

    monkeypatch.setattr(observability.settings, "enable_optional_observability", True)
    monkeypatch.setattr(observability.settings, "sentry_dsn", "https://x@y.ingest.sentry.io/1")
    monkeypatch.setattr(observability.settings, "sentry_environment", "test")
    monkeypatch.setattr(observability.settings, "sentry_traces_sample_rate", 0.0)

    class DummyCurrent:
        def __init__(self, client):
            self.client = client

    class DummyHub:
        current = DummyCurrent(None)

    called = {"init": False}

    def _fake_init(**_kwargs):
        called["init"] = True

    monkeypatch.setattr(sentry_sdk, "Hub", DummyHub)
    monkeypatch.setattr(sentry_sdk, "init", _fake_init)
    assert observability.configure_sentry() is True
    assert called["init"] is True

    DummyHub.current.client = object()
    assert observability.configure_sentry() is False


def test_configure_observability_aggregates(monkeypatch):
    app = FastAPI()
    monkeypatch.setattr(observability, "configure_structured_logging", lambda: True)
    monkeypatch.setattr(observability, "configure_metrics", lambda _app: False)
    monkeypatch.setattr(observability, "configure_tracing", lambda _app: True)
    monkeypatch.setattr(observability, "configure_sentry", lambda: False)
    result = observability.configure_observability(app)
    assert result == {"logging": True, "metrics": False, "tracing": True, "sentry": False}
