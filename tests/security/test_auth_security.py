from datetime import datetime, timedelta, timezone

import pytest
from app import models
from app.config import settings
from jose import jwt

pytestmark = [pytest.mark.integration, pytest.mark.security]


def _expired_token(user_id: int) -> str:
    payload = {
        "user_id": user_id,
        "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def _forged_token(user_id: int) -> str:
    payload = {
        "user_id": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=30),
    }
    return jwt.encode(payload, "wrong-secret", algorithm=settings.algorithm)


def test_expired_token_is_rejected(client, test_user):
    token = _expired_token(test_user["id"])
    response = client.get("/api/v1/posts/", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_forged_token_is_rejected(client, test_user):
    token = _forged_token(test_user["id"])
    response = client.get("/api/v1/posts/", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_malformed_authorization_header_is_rejected(client):
    response = client.get(
        "/api/v1/posts/",
        headers={"Authorization": "Token definitely-not-a-bearer-token"},
    )
    assert response.status_code == 401


def test_login_resists_sql_injection_like_input(client):
    response = client.post(
        "/api/v1/login",
        data={
            "username": "' OR 1=1 --",
            "password": "' OR 1=1 --",
        },
    )
    assert response.status_code in {403, 422}


def test_create_user_does_not_echo_password_and_stores_hash(client, session):
    response = client.post(
        "/api/v1/users/",
        json={"email": "security_hash_test@example.com", "password": "password123"},
    )
    assert response.status_code == 201
    payload = response.json()
    assert "password" not in payload

    db_user = (
        session.query(models.User)
        .filter(models.User.email == "security_hash_test@example.com")
        .first()
    )
    assert db_user is not None
    assert db_user.password != "password123"


def test_allowed_cors_origin_is_returned(client):
    response = client.options(
        "/api/v1/posts/",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_disallowed_cors_origin_is_not_allowed(client):
    response = client.options(
        "/api/v1/posts/",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers
