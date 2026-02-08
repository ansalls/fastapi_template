import pytest
from app import rate_limit
from fastapi import HTTPException, Response
from redis.exceptions import RedisError
from starlette.requests import Request

pytestmark = pytest.mark.unit


def _request(path="/posts/", headers=None, client=("127.0.0.1", 12345)):
    headers = headers or []
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "path": path,
        "raw_path": path.encode("utf-8"),
        "query_string": b"",
        "headers": headers,
        "client": client,
        "server": ("testserver", 80),
        "scheme": "http",
        "root_path": "",
    }
    return Request(scope)


def test_policy_loading_and_key_generation():
    policies = rate_limit._load_policies()
    assert {"auth_login", "auth_register", "api_read", "api_write"} <= set(
        policies.keys()
    )
    key = rate_limit.build_rate_limit_key(
        policies["api_read"], "user:42", now_seconds=60.0
    )
    assert key.startswith("rl:api_read:1:")


def test_client_ip_resolution_and_principal(monkeypatch):
    request = _request(headers=[(b"x-forwarded-for", b"10.1.1.1, 10.1.1.2")])
    assert rate_limit._client_ip(request) == "10.1.1.1"

    no_client_request = _request(client=None)  # type: ignore[arg-type]
    assert rate_limit._client_ip(no_client_request) == "unknown"

    auth_request = _request(headers=[(b"authorization", b"Bearer token-value")])
    monkeypatch.setattr(rate_limit.oauth2, "get_user_id_from_access_token", lambda _t: 7)
    assert rate_limit._principal_for_request(auth_request) == "user:7"

    monkeypatch.setattr(
        rate_limit.oauth2, "get_user_id_from_access_token", lambda _t: None
    )
    assert rate_limit._principal_for_request(auth_request).startswith("ip:")


def test_redis_rate_limiter_check_uses_eval_script():
    class DummyRedis:
        def eval(self, _script, _numkeys, _key, _window):
            return [3, 22]

    limiter = rate_limit.RedisRateLimiter(redis_factory=lambda: DummyRedis())
    policy = rate_limit.RateLimitPolicy(name="api_read", limit=5, window_seconds=60)
    allowed, remaining, retry_after = limiter.check(policy, "user:1")
    assert allowed is True
    assert remaining == 2
    assert retry_after == 22


def test_rate_limit_dependency_requires_known_policy():
    with pytest.raises(ValueError):
        rate_limit.rate_limit_dependency("does-not-exist")


def test_rate_limit_dependency_disabled_short_circuits(monkeypatch):
    monkeypatch.setattr(rate_limit.settings, "enable_optional_rate_limiting", False)
    dependency = rate_limit.rate_limit_dependency("api_read").dependency
    request = _request()
    response = Response()
    dependency(request, response)


def test_rate_limit_dependency_handles_backend_errors(monkeypatch):
    class BrokenLimiter:
        def check(self, _policy, _principal):
            raise RedisError("down")

    rate_limit.set_rate_limiter(BrokenLimiter())  # type: ignore[arg-type]
    dependency = rate_limit.rate_limit_dependency("api_read").dependency
    request = _request()
    response = Response()

    monkeypatch.setattr(rate_limit.settings, "enable_optional_rate_limiting", True)
    monkeypatch.setattr(rate_limit.settings, "rate_limit_enabled", True)
    monkeypatch.setattr(rate_limit.settings, "rate_limit_fail_open", True)
    dependency(request, response)

    monkeypatch.setattr(rate_limit.settings, "rate_limit_fail_open", False)
    with pytest.raises(HTTPException) as exc:
        dependency(request, response)
    assert exc.value.status_code == 503


def test_rate_limit_dependency_sets_headers_and_raises_429(monkeypatch):
    class FakeLimiter:
        def __init__(self, allowed):
            self.allowed = allowed

        def check(self, _policy, _principal):
            if self.allowed:
                return True, 9, 10
            return False, 0, 5

    monkeypatch.setattr(rate_limit.settings, "enable_optional_rate_limiting", True)
    monkeypatch.setattr(rate_limit.settings, "rate_limit_enabled", True)
    monkeypatch.setattr(rate_limit.settings, "rate_limit_fail_open", True)
    dependency = rate_limit.rate_limit_dependency("api_read").dependency
    request = _request()

    rate_limit.set_rate_limiter(FakeLimiter(True))  # type: ignore[arg-type]
    success_response = Response()
    dependency(request, success_response)
    assert success_response.headers["X-RateLimit-Remaining"] == "9"

    rate_limit.set_rate_limiter(FakeLimiter(False))  # type: ignore[arg-type]
    with pytest.raises(HTTPException) as exc:
        dependency(request, Response())
    assert exc.value.status_code == 429
