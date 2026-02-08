import jwt
import pytest
from app import schemas
from app.config import settings

pytestmark = pytest.mark.integration


# def test_root(client):
#     res = client.get("/")
#     print(res.json().get('message'))
#     assert res.json().get('message') == 'Hello World'
#     assert res.status_code == 200


def test_create_user(client):
    res = client.post(
        "/api/v1/users/", json={"email": "hello123@gmail.com", "password": "password123"}
    )
    new_user = schemas.UserOut(**res.json())
    assert new_user.email == "hello123@gmail.com"
    assert res.status_code == 201


@pytest.mark.parametrize("password", ["short", "1234567", ""])
def test_create_user_rejects_short_passwords(client, password):
    res = client.post(
        "/api/v1/users/", json={"email": "password-policy@example.com", "password": password}
    )
    assert res.status_code == 422


def test_create_user_rejects_invalid_email(client):
    res = client.post(
        "/api/v1/users/", json={"email": "not-an-email", "password": "password123"}
    )
    assert res.status_code == 422


def test_login_user(test_user, client):
    res = client.post(
        "/api/v1/login",
        data={"username": test_user["email"], "password": test_user["password"]},
    )
    login_res = schemas.Token(**res.json())
    payload = jwt.decode(
        login_res.access_token,
        settings.secret_key,
        algorithms=[settings.algorithm],
        audience=settings.token_audience,
        issuer=settings.token_issuer,
    )
    id = payload.get("user_id")
    assert id == test_user["id"]
    assert login_res.token_type == "bearer"
    assert res.status_code == 200


@pytest.mark.parametrize(
    "email, password, status_code",
    [
        ("wrongemail@gmail.com", "password123", 403),
        ("template@example.com", "wrong_password", 403),
        ("wrongemail@gmail.com", "wrong_password", 403),
        (None, "password123", 422),
        ("template@example.com", None, 422),
    ],
)
def test_incorrect_login(client, email, password, status_code):
    res = client.post("/api/v1/login", data={"username": email, "password": password})
    assert res.status_code == status_code
    # assert res.json().get('detail') == 'Invalid Credentials'
