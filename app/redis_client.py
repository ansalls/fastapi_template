from __future__ import annotations

from functools import lru_cache

from redis import Redis
from redis.exceptions import RedisError

from .config import settings


@lru_cache(maxsize=1)
def get_redis_client() -> Redis:
    return Redis.from_url(settings.redis_url, decode_responses=True)


def reset_redis_client() -> None:
    get_redis_client.cache_clear()


def ping_redis() -> bool:
    try:
        return bool(get_redis_client().ping())
    except RedisError:
        return False
