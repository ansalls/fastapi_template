import pytest
from app import oauth_external
from app.config import settings

pytestmark = pytest.mark.integration


def test_oauth_providers_empty_when_unconfigured(client, monkeypatch):
    for provider in ["google", "microsoft", "apple", "facebook", "github"]:
        monkeypatch.setattr(settings, f"oauth_{provider}_client_id", None)
        monkeypatch.setattr(settings, f"oauth_{provider}_client_secret", None)

    response = client.get("/api/v1/auth/oauth/providers")
    assert response.status_code == 200
    assert response.json() == {"providers": []}


def test_oauth_providers_lists_configured_provider(client, monkeypatch):
    for provider in ["google", "microsoft", "apple", "facebook", "github"]:
        monkeypatch.setattr(settings, f"oauth_{provider}_client_id", None)
        monkeypatch.setattr(settings, f"oauth_{provider}_client_secret", None)

    monkeypatch.setattr(settings, "oauth_github_client_id", "github-id")
    monkeypatch.setattr(settings, "oauth_github_client_secret", "github-secret")

    response = client.get("/api/v1/auth/oauth/providers")
    assert response.status_code == 200
    payload = response.json()["providers"]
    assert payload == [
        {
            "provider": "github",
            "display_name": "GitHub",
            "start_url": "/api/v1/auth/oauth/github/start",
        }
    ]


def test_oauth_start_redirects_to_provider(client, monkeypatch):
    monkeypatch.setattr(
        oauth_external,
        "build_authorization_url",
        lambda *_args, **_kwargs: "https://oauth.example/authorize",
    )
    response = client.get("/api/v1/auth/oauth/github/start", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "https://oauth.example/authorize"


def test_oauth_error_message_default_text():
    from app.routers import auth

    assert auth._oauth_error_message(None, None) == "OAuth authentication failed"


def test_oauth_callback_requires_state(client):
    response = client.get("/api/v1/auth/oauth/github/callback")
    assert response.status_code == 400
    assert response.json()["error_code"] == "invalid_oauth_state"


def test_oauth_callback_provider_error_redirects_when_frontend_mode(client, monkeypatch):
    monkeypatch.setattr(
        oauth_external,
        "parse_oauth_state",
        lambda *_args, **_kwargs: oauth_external.OAuthState(
            provider="github",
            code_verifier="verifier",
            redirect_to_frontend=True,
        ),
    )

    response = client.get(
        "/api/v1/auth/oauth/github/callback",
        params={
            "state": "state-token",
            "error": "access_denied",
            "error_description": "Denied",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["location"] == "/#provider=github&error=Denied"


def test_oauth_callback_provider_error_json_mode(client, monkeypatch):
    monkeypatch.setattr(
        oauth_external,
        "parse_oauth_state",
        lambda *_args, **_kwargs: oauth_external.OAuthState(
            provider="github",
            code_verifier="verifier",
            redirect_to_frontend=False,
        ),
    )

    response = client.get(
        "/api/v1/auth/oauth/github/callback",
        params={"state": "state-token", "error": "access_denied"},
    )

    assert response.status_code == 400
    assert response.json()["error_code"] == "oauth_provider_error"


def test_oauth_callback_requires_code_when_no_error(client, monkeypatch):
    monkeypatch.setattr(
        oauth_external,
        "parse_oauth_state",
        lambda *_args, **_kwargs: oauth_external.OAuthState(
            provider="github",
            code_verifier="verifier",
            redirect_to_frontend=False,
        ),
    )

    response = client.get(
        "/api/v1/auth/oauth/github/callback",
        params={"state": "state-token"},
    )

    assert response.status_code == 400
    assert response.json()["error_code"] == "oauth_code_missing"


def test_oauth_callback_success_redirect_mode(client, monkeypatch):
    token = oauth_external.schemas.Token(
        access_token="access",
        token_type="bearer",
        refresh_token="refresh",
    )
    monkeypatch.setattr(
        oauth_external,
        "parse_oauth_state",
        lambda *_args, **_kwargs: oauth_external.OAuthState(
            provider="github",
            code_verifier="verifier",
            redirect_to_frontend=True,
        ),
    )
    monkeypatch.setattr(
        oauth_external,
        "authenticate_oauth_callback",
        lambda *_args, **_kwargs: (token, True),
    )
    monkeypatch.setattr(
        oauth_external,
        "build_frontend_success_redirect",
        lambda *_args, **_kwargs: "/#provider=github&access_token=access",
    )

    response = client.get(
        "/api/v1/auth/oauth/github/callback",
        params={"state": "state-token", "code": "provider-code"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["location"] == "/#provider=github&access_token=access"


def test_oauth_callback_success_json_mode(client, monkeypatch):
    token = oauth_external.schemas.Token(
        access_token="access",
        token_type="bearer",
        refresh_token="refresh",
    )
    monkeypatch.setattr(
        oauth_external,
        "parse_oauth_state",
        lambda *_args, **_kwargs: oauth_external.OAuthState(
            provider="github",
            code_verifier="verifier",
            redirect_to_frontend=False,
        ),
    )
    monkeypatch.setattr(
        oauth_external,
        "authenticate_oauth_callback",
        lambda *_args, **_kwargs: (token, False),
    )

    response = client.get(
        "/api/v1/auth/oauth/github/callback",
        params={"state": "state-token", "code": "provider-code"},
    )

    assert response.status_code == 200
    assert response.json()["access_token"] == "access"


def test_oauth_callback_post_path(client, monkeypatch):
    token = oauth_external.schemas.Token(
        access_token="access",
        token_type="bearer",
        refresh_token="refresh",
    )
    monkeypatch.setattr(
        oauth_external,
        "parse_oauth_state",
        lambda *_args, **_kwargs: oauth_external.OAuthState(
            provider="github",
            code_verifier="verifier",
            redirect_to_frontend=False,
        ),
    )
    monkeypatch.setattr(
        oauth_external,
        "authenticate_oauth_callback",
        lambda *_args, **_kwargs: (token, False),
    )

    response = client.post(
        "/api/v1/auth/oauth/github/callback",
        data={"state": "state-token", "code": "provider-code"},
    )

    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"
