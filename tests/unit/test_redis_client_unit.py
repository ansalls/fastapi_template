import pytest
from app import redis_client
from redis.exceptions import RedisError

pytestmark = pytest.mark.unit


def test_get_redis_client_uses_configured_url(monkeypatch):
    redis_client.reset_redis_client()
    captured = {}

    class DummyRedis:
        pass

    def _from_url(url, decode_responses):
        captured["url"] = url
        captured["decode"] = decode_responses
        return DummyRedis()

    monkeypatch.setattr(redis_client.Redis, "from_url", _from_url)
    client = redis_client.get_redis_client()

    assert isinstance(client, DummyRedis)
    assert captured["url"] == redis_client.settings.redis_url
    assert captured["decode"] is True


def test_ping_redis_handles_success_and_failure(monkeypatch):
    class HealthyRedis:
        def ping(self):
            return True

    class BrokenRedis:
        def ping(self):
            raise RedisError("nope")

    redis_client.reset_redis_client()
    monkeypatch.setattr(redis_client, "get_redis_client", lambda: HealthyRedis())
    assert redis_client.ping_redis() is True

    monkeypatch.setattr(redis_client, "get_redis_client", lambda: BrokenRedis())
    assert redis_client.ping_redis() is False
