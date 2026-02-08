from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt import InvalidTokenError
from sqlalchemy.orm import Session

from . import database, models, schemas
from .config import settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/login")

SECRET_KEY = settings.secret_key
ALGORITHM = settings.algorithm
TOKEN_ISSUER = settings.token_issuer
TOKEN_AUDIENCE = settings.token_audience
ACCESS_TOKEN_EXPIRE_MINUTES = settings.access_token_expire_minutes
REFRESH_TOKEN_EXPIRE_DAYS = settings.refresh_token_expire_days

ACCESS_TOKEN_TYPE = "access"  # nosec B105
REFRESH_TOKEN_TYPE = "refresh"  # nosec B105
BEARER_TOKEN_TYPE = "bearer"  # nosec B105


def _to_utc_datetime(exp: Any) -> datetime:
    if isinstance(exp, datetime):
        return exp.astimezone(timezone.utc)
    if isinstance(exp, (int, float)):
        return datetime.fromtimestamp(exp, tz=timezone.utc)
    raise ValueError("Token expiry is invalid")


def _decode_token(
    token: str, *, required_claims: tuple[str, ...] = ("exp",)
) -> dict[str, Any]:
    payload = jwt.decode(
        token,
        SECRET_KEY,
        algorithms=[ALGORITHM],
        audience=TOKEN_AUDIENCE,
        issuer=TOKEN_ISSUER,
        options={"require": list(required_claims)},
    )
    if not isinstance(payload, dict):
        raise InvalidTokenError("Invalid payload")
    return payload


def _build_refresh_credentials_exception() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={
            "detail": "Could not validate refresh token",
            "error_code": "invalid_refresh_token",
        },
        headers={"WWW-Authenticate": "Bearer"},
    )


def create_access_token(
    data: dict[str, Any], expires_minutes: int | None = None
) -> str:
    to_encode = data.copy()
    expire_minutes = (
        ACCESS_TOKEN_EXPIRE_MINUTES if expires_minutes is None else expires_minutes
    )
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=expire_minutes)
    to_encode.update(
        {
            "iss": TOKEN_ISSUER,
            "aud": TOKEN_AUDIENCE,
            "iat": now,
            "nbf": now,
            "exp": expire,
            "jti": uuid.uuid4().hex,
            "token_type": ACCESS_TOKEN_TYPE,
        }
    )
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(data: dict[str, Any], expires_days: int | None = None) -> str:
    to_encode = data.copy()
    expire_days = REFRESH_TOKEN_EXPIRE_DAYS if expires_days is None else expires_days
    now = datetime.now(timezone.utc)
    expire = now + timedelta(days=expire_days)
    to_encode.update(
        {
            "iss": TOKEN_ISSUER,
            "aud": TOKEN_AUDIENCE,
            "iat": now,
            "nbf": now,
            "exp": expire,
            "token_type": REFRESH_TOKEN_TYPE,
            "jti": uuid.uuid4().hex,
        }
    )
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_user_id_from_access_token(token: str) -> int | None:
    try:
        payload = _decode_token(token, required_claims=("exp", "user_id", "token_type"))
    except InvalidTokenError:
        return None

    token_type = payload.get("token_type", ACCESS_TOKEN_TYPE)
    if token_type != ACCESS_TOKEN_TYPE:
        return None

    try:
        return int(payload["user_id"])
    except (TypeError, ValueError):
        return None


def verify_access_token(
    token: str, credentials_exception: HTTPException
) -> schemas.TokenData:
    try:
        payload = _decode_token(
            token,
            required_claims=("exp", "user_id", "token_type"),
        )
        token_type = payload.get("token_type")
        if token_type != ACCESS_TOKEN_TYPE:
            raise credentials_exception

        token_data = schemas.TokenData(id=int(payload["user_id"]))
    except (InvalidTokenError, ValueError, TypeError):
        raise credentials_exception

    return token_data


def verify_refresh_token(token: str) -> dict[str, Any]:
    credentials_exception = _build_refresh_credentials_exception()
    try:
        payload = _decode_token(
            token,
            required_claims=("exp", "user_id", "token_type", "jti"),
        )
        if payload.get("token_type") != REFRESH_TOKEN_TYPE:
            raise credentials_exception

        payload["user_id"] = int(payload["user_id"])
        payload["jti"] = str(payload["jti"])
        payload["exp"] = _to_utc_datetime(payload["exp"])
        return payload
    except (InvalidTokenError, ValueError, TypeError):
        raise credentials_exception


def _persist_refresh_token(
    db: Session,
    *,
    user_id: int,
    jti: str,
    expires_at: datetime,
    rotated_from_jti: str | None = None,
) -> models.RefreshToken:
    refresh_record = models.RefreshToken(
        user_id=user_id,
        jti=jti,
        expires_at=expires_at,
        rotated_from_jti=rotated_from_jti,
    )
    db.add(refresh_record)
    return refresh_record


def issue_token_pair(db: Session, user_id: int) -> schemas.Token:
    access_token = create_access_token(data={"user_id": user_id})
    refresh_token = create_refresh_token(data={"user_id": user_id})
    payload = verify_refresh_token(refresh_token)
    _persist_refresh_token(
        db,
        user_id=user_id,
        jti=payload["jti"],
        expires_at=payload["exp"],
    )
    db.commit()
    return schemas.Token(
        access_token=access_token,
        token_type=BEARER_TOKEN_TYPE,
        refresh_token=refresh_token,
    )


def rotate_refresh_token(db: Session, refresh_token: str) -> schemas.Token:
    payload = verify_refresh_token(refresh_token)
    existing_token = (
        db.query(models.RefreshToken)
        .filter(models.RefreshToken.jti == payload["jti"])
        .first()
    )
    if existing_token is None or existing_token.revoked:
        raise _build_refresh_credentials_exception()
    if existing_token.expires_at <= datetime.now(timezone.utc):
        existing_token.revoked = True  # type: ignore[assignment]
        db.commit()
        raise _build_refresh_credentials_exception()

    existing_token.revoked = True  # type: ignore[assignment]
    access_token = create_access_token(data={"user_id": payload["user_id"]})
    new_refresh_token = create_refresh_token(data={"user_id": payload["user_id"]})
    new_payload = verify_refresh_token(new_refresh_token)
    existing_token.replaced_by_jti = new_payload["jti"]
    _persist_refresh_token(
        db,
        user_id=payload["user_id"],
        jti=new_payload["jti"],
        expires_at=new_payload["exp"],
        rotated_from_jti=payload["jti"],
    )
    db.commit()
    return schemas.Token(
        access_token=access_token,
        token_type=BEARER_TOKEN_TYPE,
        refresh_token=new_refresh_token,
    )


def revoke_refresh_token(db: Session, refresh_token: str) -> bool:
    payload = verify_refresh_token(refresh_token)
    existing_token = (
        db.query(models.RefreshToken)
        .filter(models.RefreshToken.jti == payload["jti"])
        .first()
    )
    if existing_token is None:
        return False
    if not existing_token.revoked:
        existing_token.revoked = True  # type: ignore[assignment]
        db.commit()
    return True


def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(database.get_db)
) -> models.User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={
            "detail": "Could not validate credentials",
            "error_code": "invalid_credentials",
        },
        headers={"WWW-Authenticate": "Bearer"},
    )

    token_data = verify_access_token(token, credentials_exception)
    user = db.query(models.User).filter(models.User.id == token_data.id).first()
    if user is None:
        raise credentials_exception
    return user
