import uuid
from datetime import datetime, timedelta, timezone

import pytest
from app import models, oauth2
from fastapi import HTTPException, status
from jose import JWTError, jwt

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


def test_decode_token_rejects_non_dict_payload(monkeypatch):
    monkeypatch.setattr(oauth2.jwt, "decode", lambda *_args, **_kwargs: "not-a-dict")
    with pytest.raises(JWTError):
        oauth2._decode_token("token-value")


def test_to_utc_datetime_variants():
    now = datetime.now(timezone.utc)
    assert oauth2._to_utc_datetime(now).tzinfo is not None
    unix_exp = int(now.timestamp())
    assert oauth2._to_utc_datetime(unix_exp).tzinfo is not None
    with pytest.raises(ValueError):
        oauth2._to_utc_datetime("oops")


def test_get_user_id_from_access_token_variants():
    valid = oauth2.create_access_token({"user_id": 321})
    assert oauth2.get_user_id_from_access_token(valid) == 321

    assert oauth2.get_user_id_from_access_token("not-a-token") is None

    refresh_token = oauth2.create_refresh_token({"user_id": 321})
    assert oauth2.get_user_id_from_access_token(refresh_token) is None

    no_user_token = oauth2.create_access_token({})
    assert oauth2.get_user_id_from_access_token(no_user_token) is None

    bad_user_token = oauth2.create_access_token({"user_id": "not-int"})
    assert oauth2.get_user_id_from_access_token(bad_user_token) is None


def test_verify_access_token_rejects_wrong_token_type():
    refresh_token = oauth2.create_refresh_token({"user_id": 1})
    with pytest.raises(HTTPException):
        oauth2.verify_access_token(refresh_token, credentials_exception())


def test_verify_refresh_token_rejects_missing_fields():
    incomplete_payload = {
        "user_id": 1,
        "token_type": oauth2.REFRESH_TOKEN_TYPE,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
    }
    token = jwt.encode(incomplete_payload, oauth2.SECRET_KEY, algorithm=oauth2.ALGORITHM)
    with pytest.raises(HTTPException):
        oauth2.verify_refresh_token(token)


def test_verify_refresh_token_rejects_wrong_type():
    token = oauth2.create_access_token({"user_id": 1})
    with pytest.raises(HTTPException):
        oauth2.verify_refresh_token(token)


def test_verify_refresh_token_rejects_invalid_token():
    with pytest.raises(HTTPException):
        oauth2.verify_refresh_token("not-a-token")


@pytest.mark.integration
def test_issue_token_pair_and_refresh_lifecycle(session):
    email = f"user_{uuid.uuid4().hex[:8]}@example.com"
    user = models.User(email=email, password="hashed-password")
    session.add(user)
    session.commit()
    session.refresh(user)

    pair = oauth2.issue_token_pair(session, int(user.id))
    assert pair.refresh_token is not None
    stored_tokens = (
        session.query(models.RefreshToken)
        .filter(models.RefreshToken.user_id == user.id)
        .all()
    )
    assert len(stored_tokens) == 1
    assert stored_tokens[0].revoked is False

    rotated = oauth2.rotate_refresh_token(session, pair.refresh_token)
    assert rotated.refresh_token is not None
    session.refresh(stored_tokens[0])
    assert stored_tokens[0].revoked is True
    assert stored_tokens[0].replaced_by_jti is not None

    with pytest.raises(HTTPException):
        oauth2.rotate_refresh_token(session, pair.refresh_token)

    assert oauth2.revoke_refresh_token(session, rotated.refresh_token) is True
    assert oauth2.revoke_refresh_token(session, rotated.refresh_token) is True


@pytest.mark.integration
def test_rotate_refresh_token_rejects_unknown_and_expired(session):
    email = f"user_{uuid.uuid4().hex[:8]}@example.com"
    user = models.User(email=email, password="hashed-password")
    session.add(user)
    session.commit()
    session.refresh(user)

    orphan_refresh = oauth2.create_refresh_token({"user_id": int(user.id)})
    assert oauth2.revoke_refresh_token(session, orphan_refresh) is False
    with pytest.raises(HTTPException):
        oauth2.rotate_refresh_token(session, orphan_refresh)

    pair = oauth2.issue_token_pair(session, int(user.id))
    payload = oauth2.verify_refresh_token(pair.refresh_token)
    token_row = (
        session.query(models.RefreshToken)
        .filter(models.RefreshToken.jti == payload["jti"])
        .first()
    )
    token_row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    session.commit()

    with pytest.raises(HTTPException):
        oauth2.rotate_refresh_token(session, pair.refresh_token)
