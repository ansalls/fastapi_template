from app import schemas


def test_get_user_by_id_returns_user(client, test_user):
    response = client.get(f"/users/{test_user['id']}")

    assert response.status_code == 200
    found_user = schemas.UserOut(**response.json())
    assert found_user.id == test_user["id"]
    assert found_user.email == test_user["email"]


def test_get_user_not_found_returns_404(client):
    response = client.get("/users/999999")

    assert response.status_code == 404
    assert response.json()["detail"] == "User with id: 999999 does not exist"


def test_create_user_duplicate_email_returns_conflict(client, test_user):
    duplicate_response = client.post(
        "/users/",
        json={"email": test_user["email"], "password": "password123"},
    )

    assert duplicate_response.status_code == 409
    assert duplicate_response.json()["detail"] == "Email is already registered"
