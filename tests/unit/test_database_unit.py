import pytest

from app import database


class DummySession:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


def test_get_db_yields_session_and_closes(monkeypatch):
    dummy_session = DummySession()
    monkeypatch.setattr(database, "SessionLocal", lambda: dummy_session)

    session_generator = database.get_db()
    assert next(session_generator) is dummy_session

    with pytest.raises(StopIteration):
        next(session_generator)

    assert dummy_session.closed is True
