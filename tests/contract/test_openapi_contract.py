import pytest

pytestmark = [pytest.mark.integration, pytest.mark.contract]


def test_openapi_exposes_expected_core_paths(client):
    schema = client.get("/openapi.json").json()
    paths = schema["paths"]

    assert "/api/v1/login" in paths
    assert "/api/v1/auth/oauth/providers" in paths
    assert "/api/v1/auth/oauth/{provider}/start" in paths
    assert "/api/v1/auth/oauth/{provider}/link/start" in paths
    assert "/api/v1/auth/oauth/{provider}/callback" in paths
    assert "/api/v1/users/" in paths
    assert "/api/v1/posts/" in paths
    assert "/api/v1/vote/" in paths
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
    login_post = schema["paths"]["/api/v1/login"]["post"]
    request_body = login_post["requestBody"]["content"]

    assert "application/x-www-form-urlencoded" in request_body
    assert login_post["responses"]["200"]["description"] == "Successful Response"


def test_posts_endpoint_contract_requires_auth(client):
    schema = client.get("/openapi.json").json()
    posts_get = schema["paths"]["/api/v1/posts/"]["get"]
    security = posts_get.get("security", [])

    assert {"OAuth2PasswordBearer": []} in security


def test_user_creation_contract_excludes_password_in_response(client):
    schema = client.get("/openapi.json").json()
    users_post = schema["paths"]["/api/v1/users/"]["post"]
    response_schema_ref = users_post["responses"]["201"]["content"]["application/json"][
        "schema"
    ]["$ref"]

    assert response_schema_ref.endswith("/UserOut")
    user_out_props = schema["components"]["schemas"]["UserOut"]["properties"]
    assert "password" not in user_out_props


def test_validation_contracts_are_exposed_in_openapi(client):
    schema = client.get("/openapi.json").json()

    user_create = schema["components"]["schemas"]["UserCreate"]
    assert user_create["properties"]["password"]["minLength"] == 8

    vote = schema["components"]["schemas"]["Vote"]
    assert vote["properties"]["post_id"]["exclusiveMinimum"] == 0
    assert vote["properties"]["dir"]["minimum"] == 0
    assert vote["properties"]["dir"]["maximum"] == 1

    posts_params = schema["paths"]["/api/v1/posts/"]["get"]["parameters"]
    limit_param = next(param for param in posts_params if param["name"] == "limit")
    skip_param = next(param for param in posts_params if param["name"] == "skip")
    assert limit_param["schema"]["minimum"] == 1
    assert limit_param["schema"]["maximum"] == 100
    assert skip_param["schema"]["minimum"] == 0
