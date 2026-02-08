from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from arq import cron
from arq.connections import RedisSettings
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models import OutboxEvent
from app.outbox import get_pending_outbox_events, mark_outbox_event_completed


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _dispatch_second_schedule() -> set[int]:
    interval = max(1, min(settings.outbox_dispatch_interval_seconds, 60))
    return set(range(0, 60, interval))


def _retry_delay_seconds(attempt: int) -> int:
    base = max(settings.outbox_retry_backoff_seconds, 1)
    clamped_attempt = max(attempt, 1)
    # Exponential backoff with a practical cap for template defaults.
    return min(base * (2 ** (clamped_attempt - 1)), 3600)


def _mark_event_pending_retry(event: OutboxEvent, error: str) -> None:
    attempt = int(event.attempts) + 1
    event.status = "pending"
    event.attempts = attempt
    event.last_error = error
    event.available_at = _now_utc() + timedelta(seconds=_retry_delay_seconds(attempt))


def _mark_event_failed_terminal(event: OutboxEvent, error: str) -> None:
    attempt = int(event.attempts) + 1
    event.status = "failed"
    event.attempts = attempt
    event.last_error = error
    event.processed_at = _now_utc()


async def process_outbox_event(_ctx: dict[str, Any], event_id: int) -> dict[str, str]:
    db: Session = SessionLocal()
    try:
        event = db.query(OutboxEvent).filter(OutboxEvent.id == event_id).first()
        if event is None:
            return {"status": "missing", "event_id": str(event_id)}

        try:
            # Template placeholder for external delivery. Real templates should
            # dispatch by topic and integrate provider-specific delivery logic.
            mark_outbox_event_completed(db, event)
            db.commit()
            return {"status": "completed", "event_id": str(event_id)}
        except Exception as exc:  # pragma: no cover - defensive reliability path
            if int(event.attempts) + 1 >= settings.outbox_retry_max_attempts:
                _mark_event_failed_terminal(event, str(exc))
            else:
                _mark_event_pending_retry(event, str(exc))
            db.commit()
            return {"status": "retry_scheduled", "event_id": str(event_id)}
    finally:
        db.close()


async def dispatch_outbox(ctx: dict[str, Any]) -> dict[str, int]:
    db: Session = SessionLocal()
    scheduled = 0
    try:
        now = _now_utc()
        events = get_pending_outbox_events(
            db, limit=max(1, settings.outbox_dispatch_batch_size)
        )
        for event in events:
            if event.available_at and event.available_at > now:
                continue
            try:
                event.status = "queued"
                event.last_error = None
                await ctx["redis"].enqueue_job("process_outbox_event", int(event.id))
                scheduled += 1
            except Exception as exc:  # pragma: no cover - defensive reliability path
                _mark_event_pending_retry(event, f"enqueue_failed: {exc}")
        db.commit()
    finally:
        db.close()
    return {"scheduled": scheduled}


class WorkerSettings:
    functions = [dispatch_outbox, process_outbox_event]
    cron_jobs = [
        cron(
            dispatch_outbox,
            second=_dispatch_second_schedule(),
            microsecond=0,
            run_at_startup=True,
            unique=True,
        )
    ]
    on_startup = None
    on_shutdown = None
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    burst = False
