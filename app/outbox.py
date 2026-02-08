from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from .models import OutboxEvent


def enqueue_outbox_event(
    db: Session, *, topic: str, payload: dict[str, Any]
) -> OutboxEvent:
    event = OutboxEvent(topic=topic, payload=payload)
    db.add(event)
    return event


def get_pending_outbox_events(db: Session, limit: int = 100) -> list[OutboxEvent]:
    return (
        db.query(OutboxEvent)
        .filter(OutboxEvent.status == "pending")
        .order_by(OutboxEvent.created_at.asc())
        .limit(limit)
        .all()
    )


def mark_outbox_event_completed(db: Session, event: OutboxEvent) -> None:
    event.status = "completed"  # type: ignore[assignment]
    event.processed_at = datetime.now(timezone.utc)  # type: ignore[assignment]


def mark_outbox_event_failed(db: Session, event: OutboxEvent, error: str) -> None:
    event.status = "failed"  # type: ignore[assignment]
    event.last_error = error  # type: ignore[assignment]
    event.attempts = int(event.attempts) + 1  # type: ignore[assignment]
    event.processed_at = datetime.now(timezone.utc)  # type: ignore[assignment]
