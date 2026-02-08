from datetime import datetime, timedelta, timezone

import pytest
from app import oauth2
from fastapi import HTTPException, status
from jose import jwt

pytestmark = pytest.mark.unit


def credentials_exception():
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def test_verify_access_token_rejects_missing_user_id():
    token = jwt.encode(
        {"exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
        oauth2.SECRET_KEY,
        algorithm=oauth2.ALGORITHM,
    )

    with pytest.raises(HTTPException) as exc_info:
        oauth2.verify_access_token(token, credentials_exception())

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED


def test_verify_access_token_rejects_invalid_token():
    with pytest.raises(HTTPException) as exc_info:
        oauth2.verify_access_token("not-a-jwt", credentials_exception())

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED


class DummyQuery:
    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return None


class DummySession:
    def query(self, *args, **kwargs):
        return DummyQuery()


def test_get_current_user_rejects_unknown_user():
    token = oauth2.create_access_token({"user_id": 999999})
    db = DummySession()

    with pytest.raises(HTTPException) as exc_info:
        oauth2.get_current_user(token=token, db=db)

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
