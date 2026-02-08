from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import Any, Callable, cast

from fastapi import Depends, HTTPException, Request, Response, status
from redis import Redis
from redis.exceptions import RedisError

from . import oauth2
from .config import settings
from .redis_client import get_redis_client

_RATE_LIMIT_LUA = """
local current = redis.call("INCR", KEYS[1])
if current == 1 then
  redis.call("EXPIRE", KEYS[1], ARGV[1])
end
local ttl = redis.call("TTL", KEYS[1])
return {current, ttl}
"""


@dataclass(frozen=True)
class RateLimitPolicy:
    name: str
    limit: int
    window_seconds: int


def _load_policies() -> dict[str, RateLimitPolicy]:
    return {
        "auth_login": RateLimitPolicy(
            "auth_login",
            settings.rate_limit_login_limit,
            settings.rate_limit_login_window_seconds,
        ),
        "auth_register": RateLimitPolicy(
            "auth_register",
            settings.rate_limit_register_limit,
            settings.rate_limit_register_window_seconds,
        ),
        "api_read": RateLimitPolicy(
            "api_read",
            settings.rate_limit_read_limit,
            settings.rate_limit_read_window_seconds,
        ),
        "api_write": RateLimitPolicy(
            "api_write",
            settings.rate_limit_write_limit,
            settings.rate_limit_write_window_seconds,
        ),
    }


def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    if request.client is None:
        return "unknown"
    return request.client.host


def _principal_for_request(request: Request) -> str:
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        token = auth_header.split(" ", 1)[1].strip()
        user_id = oauth2.get_user_id_from_access_token(token)
        if user_id is not None:
            return f"user:{user_id}"
    return f"ip:{_client_ip(request)}"


def build_rate_limit_key(
    policy: RateLimitPolicy, principal: str, now_seconds: float | None = None
) -> str:
    epoch_seconds = int(now_seconds or time.time())
    window_bucket = epoch_seconds // policy.window_seconds
    principal_hash = hashlib.sha256(principal.encode("utf-8")).hexdigest()[:16]
    return f"rl:{policy.name}:{window_bucket}:{principal_hash}"


class RedisRateLimiter:
    def __init__(self, redis_factory: Callable[[], Redis] = get_redis_client):
        self._redis_factory = redis_factory

    def check(self, policy: RateLimitPolicy, principal: str) -> tuple[bool, int, int]:
        key = build_rate_limit_key(policy, principal)
        redis_client = self._redis_factory()
        raw_result = redis_client.eval(  # type: ignore[arg-type]
            _RATE_LIMIT_LUA, 1, key, str(policy.window_seconds)
        )
        result = cast(list[Any], raw_result)
        count = int(result[0])
        ttl = max(int(result[1]), 0)
        remaining = max(policy.limit - count, 0)
        allowed = count <= policy.limit
        return allowed, remaining, ttl


_rate_limiter = RedisRateLimiter()


def set_rate_limiter(rate_limiter: RedisRateLimiter) -> None:
    global _rate_limiter
    _rate_limiter = rate_limiter


def _should_rate_limit() -> bool:
    return settings.enable_optional_rate_limiting and settings.rate_limit_enabled


def rate_limit_dependency(policy_name: str):
    policies = _load_policies()
    if policy_name not in policies:
        raise ValueError(f"Unknown rate limit policy: {policy_name}")
    policy = policies[policy_name]

    def _dependency(request: Request, response: Response) -> None:
        if not _should_rate_limit():
            return

        principal = _principal_for_request(request)
        try:
            allowed, remaining, retry_after = _rate_limiter.check(policy, principal)
        except RedisError:
            if settings.rate_limit_fail_open:
                return
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "detail": "Rate limiting backend is unavailable",
                    "error_code": "rate_limit_backend_unavailable",
                },
            )

        response.headers["X-RateLimit-Limit"] = str(policy.limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(retry_after)
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "detail": "Rate limit exceeded",
                    "error_code": "rate_limit_exceeded",
                },
                headers={"Retry-After": str(max(retry_after, 1))},
            )

    return Depends(_dependency)
