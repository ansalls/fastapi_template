import pytest
from app import health
from sqlalchemy.exc import SQLAlchemyError

pytestmark = pytest.mark.unit


class _DummyConnection:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, _query):
        return 1


def test_database_ready_true(monkeypatch):
    monkeypatch.setattr(health.engine, "connect", lambda: _DummyConnection())
    assert health.database_ready() is True


def test_database_ready_false_on_sqlalchemy_error(monkeypatch):
    def _raise_error():
        raise SQLAlchemyError("db-down")

    monkeypatch.setattr(health.engine, "connect", _raise_error)
    assert health.database_ready() is False


def test_redis_ready_behaviour(monkeypatch):
    monkeypatch.setattr(health.settings, "redis_health_required", False)
    monkeypatch.setattr(health, "ping_redis", lambda: False)
    assert health.redis_ready() is True

    monkeypatch.setattr(health.settings, "redis_health_required", True)
    monkeypatch.setattr(health, "ping_redis", lambda: False)
    assert health.redis_ready() is False

    monkeypatch.setattr(health, "ping_redis", lambda: True)
    assert health.redis_ready() is True


def test_readiness_state_reports_combined_checks(monkeypatch):
    monkeypatch.setattr(health, "database_ready", lambda: True)
    monkeypatch.setattr(health, "redis_ready", lambda: False)
    ready, checks = health.readiness_state()
    assert ready is False
    assert checks == {"database": True, "redis": False}
