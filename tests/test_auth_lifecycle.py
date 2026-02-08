import pytest

pytestmark = pytest.mark.integration


def test_login_returns_refresh_token(client, test_user):
    response = client.post(
        "/api/v1/login",
        data={"username": test_user["email"], "password": test_user["password"]},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["token_type"] == "bearer"
    assert "refresh_token" in payload
    assert payload["refresh_token"]


def test_refresh_and_logout_flow(client, test_user):
    login = client.post(
        "/api/v1/login",
        data={"username": test_user["email"], "password": test_user["password"]},
    )
    refresh_token = login.json()["refresh_token"]

    refreshed = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert refreshed.status_code == 200
    new_refresh_token = refreshed.json()["refresh_token"]
    assert new_refresh_token != refresh_token

    logout = client.post("/api/v1/auth/logout", json={"refresh_token": new_refresh_token})
    assert logout.status_code == 204

    revoked_refresh = client.post("/api/v1/auth/refresh", json={"refresh_token": new_refresh_token})
    assert revoked_refresh.status_code == 401
