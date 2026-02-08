from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from .config import settings
from .database import engine
from .redis_client import ping_redis


def database_ready() -> bool:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except SQLAlchemyError:
        return False


def redis_ready() -> bool:
    if not settings.redis_health_required:
        return True
    return ping_redis()


def readiness_state() -> tuple[bool, dict[str, bool]]:
    checks = {
        "database": database_ready(),
        "redis": redis_ready(),
    }
    return all(checks.values()), checks
