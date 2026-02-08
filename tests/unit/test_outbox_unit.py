import pytest
from app import models, outbox

pytestmark = pytest.mark.integration


def test_enqueue_and_fetch_pending_outbox_events(session):
    first = outbox.enqueue_outbox_event(
        session, topic="event.first", payload={"sequence": 1}
    )
    second = outbox.enqueue_outbox_event(
        session, topic="event.second", payload={"sequence": 2}
    )
    session.commit()

    pending = outbox.get_pending_outbox_events(session, limit=10)
    assert [event.id for event in pending] == [first.id, second.id]

    limited = outbox.get_pending_outbox_events(session, limit=1)
    assert len(limited) == 1
    assert limited[0].id == first.id


def test_mark_outbox_event_completed_and_failed(session):
    event = models.OutboxEvent(topic="event.topic", payload={"k": "v"}, attempts=0)
    session.add(event)
    session.commit()
    session.refresh(event)

    outbox.mark_outbox_event_completed(session, event)
    assert event.status == "completed"
    assert event.processed_at is not None

    outbox.mark_outbox_event_failed(session, event, "boom")
    assert event.status == "failed"
    assert event.last_error == "boom"
    assert event.attempts == 1
