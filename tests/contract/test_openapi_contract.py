import pytest

pytestmark = [pytest.mark.integration, pytest.mark.contract]


def test_openapi_exposes_expected_core_paths(client):
    schema = client.get("/openapi.json").json()
    paths = schema["paths"]

    assert "/login" in paths
    assert "/users/" in paths
    assert "/posts/" in paths
    assert "/vote/" in paths
    assert "/health" in paths
    # Root is intentionally hidden from schema.
    assert "/" not in paths


def test_openapi_uses_bearer_security_scheme(client):
    schema = client.get("/openapi.json").json()
    security_schemes = schema["components"]["securitySchemes"]
    assert "OAuth2PasswordBearer" in security_schemes
    assert security_schemes["OAuth2PasswordBearer"]["type"] == "oauth2"


def test_login_contract_requires_form_data(client):
    schema = client.get("/openapi.json").json()
    login_post = schema["paths"]["/login"]["post"]
    request_body = login_post["requestBody"]["content"]

    assert "application/x-www-form-urlencoded" in request_body
    assert login_post["responses"]["200"]["description"] == "Successful Response"


def test_posts_endpoint_contract_requires_auth(client):
    schema = client.get("/openapi.json").json()
    posts_get = schema["paths"]["/posts/"]["get"]
    security = posts_get.get("security", [])

    assert {"OAuth2PasswordBearer": []} in security


def test_user_creation_contract_excludes_password_in_response(client):
    schema = client.get("/openapi.json").json()
    users_post = schema["paths"]["/users/"]["post"]
    response_schema_ref = users_post["responses"]["201"]["content"]["application/json"][
        "schema"
    ]["$ref"]

    assert response_schema_ref.endswith("/UserOut")
    user_out_props = schema["components"]["schemas"]["UserOut"]["properties"]
    assert "password" not in user_out_props
