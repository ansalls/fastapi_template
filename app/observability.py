from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI

from .config import settings


def _route_exists(app: FastAPI, path: str) -> bool:
    return any(getattr(route, "path", None) == path for route in app.routes)


def configure_structured_logging() -> bool:
    root = logging.getLogger()
    if getattr(root, "_json_logging_configured", False):
        return False

    handler = logging.StreamHandler()
    try:
        from pythonjsonlogger.json import JsonFormatter

        handler.setFormatter(
            JsonFormatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        )
    except ImportError:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        )

    root.handlers = [handler]
    root.setLevel(logging.INFO)
    setattr(root, "_json_logging_configured", True)
    return True


def configure_metrics(app: FastAPI) -> bool:
    if not (settings.enable_optional_observability and settings.metrics_enabled):
        return False
    if _route_exists(app, "/metrics"):
        return False

    try:
        from prometheus_fastapi_instrumentator import Instrumentator
    except ImportError:
        return False

    Instrumentator().instrument(app).expose(
        app, endpoint="/metrics", include_in_schema=False
    )
    return True


def configure_tracing(app: FastAPI) -> bool:
    endpoint = settings.otel_exporter_otlp_endpoint
    if not (settings.enable_optional_observability and endpoint):
        return False
    if getattr(app.state, "otel_configured", False):
        return False

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        return False

    resource = Resource.create({"service.name": settings.otel_service_name})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app, tracer_provider=provider)
    app.state.otel_configured = True
    return True


def configure_sentry() -> bool:
    if not (settings.enable_optional_observability and settings.sentry_dsn):
        return False

    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
    except ImportError:
        return False

    if sentry_sdk.Hub.current.client is not None:
        return False

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.sentry_environment,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        integrations=[FastApiIntegration(), SqlalchemyIntegration()],
        send_default_pii=False,
    )
    return True


def configure_observability(app: FastAPI) -> dict[str, Any]:
    return {
        "logging": configure_structured_logging(),
        "metrics": configure_metrics(app),
        "tracing": configure_tracing(app),
        "sentry": configure_sentry(),
    }
