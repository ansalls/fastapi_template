from __future__ import annotations

import logging
from datetime import datetime, timezone

from arq.connections import RedisSettings
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models import OutboxEvent
from app.outbox import get_pending_outbox_events, mark_outbox_event_completed

logger = logging.getLogger(__name__)


async def process_outbox_event(_ctx, event_id: int) -> dict[str, str]:
    db: Session = SessionLocal()
    try:
        event = db.query(OutboxEvent).filter(OutboxEvent.id == event_id).first()
        if event is None:
            return {"status": "missing", "event_id": str(event_id)}
        mark_outbox_event_completed(db, event)
        db.commit()
        return {"status": "completed", "event_id": str(event_id)}
    finally:
        db.close()


async def dispatch_outbox(ctx) -> dict[str, int]:
    db: Session = SessionLocal()
    scheduled = 0
    try:
        events = get_pending_outbox_events(db, limit=100)
        for event in events:
            event.status = "processing"
            event.available_at = datetime.now(timezone.utc)
            await ctx["redis"].enqueue_job("process_outbox_event", event.id)
            scheduled += 1
        db.commit()
    finally:
        db.close()
    return {"scheduled": scheduled}


class WorkerSettings:
    functions = [dispatch_outbox, process_outbox_event]
    on_startup = None
    on_shutdown = None
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    burst = False
