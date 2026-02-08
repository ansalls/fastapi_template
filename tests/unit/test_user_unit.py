import pytest
from app import schemas

pytestmark = pytest.mark.integration


def test_get_user_by_id_returns_user(authorized_client, test_user):
    response = authorized_client.get(f"/api/v1/users/{test_user['id']}")

    assert response.status_code == 200
    found_user = schemas.UserOut(**response.json())
    assert found_user.id == test_user["id"]
    assert found_user.email == test_user["email"]


def test_get_user_requires_authentication(client, test_user):
    response = client.get(f"/api/v1/users/{test_user['id']}")
    assert response.status_code == 401


def test_get_user_unknown_id_is_forbidden(authorized_client):
    response = authorized_client.get("/api/v1/users/999999")
    assert response.status_code == 403
    assert response.json()["detail"] == "Not authorized to access this user"


def test_get_user_forbidden_for_another_user(authorized_client, test_user2):
    response = authorized_client.get(f"/api/v1/users/{test_user2['id']}")
    assert response.status_code == 403
    assert response.json()["detail"] == "Not authorized to access this user"


def test_create_user_duplicate_email_returns_conflict(client, test_user):
    duplicate_response = client.post(
        "/api/v1/users/",
        json={"email": test_user["email"], "password": "password123"},
    )

    assert duplicate_response.status_code == 409
    assert duplicate_response.json()["detail"] == "Email is already registered"
