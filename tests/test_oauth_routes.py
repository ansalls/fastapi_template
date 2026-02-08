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
            "link_start_url": "/api/v1/auth/oauth/github/link/start",
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


def test_oauth_link_start_requires_authentication(client):
    response = client.post("/api/v1/auth/oauth/github/link/start")
    assert response.status_code == 401


def test_oauth_link_start_returns_authorization_url(
    authorized_client, test_user, monkeypatch
):
    captured = {}

    def fake_build_authorization_url(*_args, **kwargs):
        captured.update(kwargs)
        return "https://oauth.example/link-authorize"

    monkeypatch.setattr(oauth_external, "build_authorization_url", fake_build_authorization_url)

    response = authorized_client.post("/api/v1/auth/oauth/github/link/start")

    assert response.status_code == 200
    assert response.json() == {"authorization_url": "https://oauth.example/link-authorize"}
    assert captured["link_user_id"] == test_user["id"]
    assert captured["redirect_to_frontend"] is True


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
        "complete_oauth_callback",
        lambda *_args, **_kwargs: oauth_external.OAuthCallbackResult(
            provider="github",
            redirect_to_frontend=True,
            token=token,
        ),
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
        "complete_oauth_callback",
        lambda *_args, **_kwargs: oauth_external.OAuthCallbackResult(
            provider="github",
            redirect_to_frontend=False,
            token=token,
        ),
    )

    response = client.get(
        "/api/v1/auth/oauth/github/callback",
        params={"state": "state-token", "code": "provider-code"},
    )

    assert response.status_code == 200
    assert response.json()["access_token"] == "access"


def test_oauth_callback_link_redirect_mode(client, monkeypatch):
    monkeypatch.setattr(
        oauth_external,
        "parse_oauth_state",
        lambda *_args, **_kwargs: oauth_external.OAuthState(
            provider="github",
            code_verifier="verifier",
            redirect_to_frontend=True,
            link_user_id=1,
        ),
    )
    monkeypatch.setattr(
        oauth_external,
        "complete_oauth_callback",
        lambda *_args, **_kwargs: oauth_external.OAuthCallbackResult(
            provider="github",
            redirect_to_frontend=True,
            linked=True,
        ),
    )

    response = client.get(
        "/api/v1/auth/oauth/github/callback",
        params={"state": "state-token", "code": "provider-code"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["location"] == "/#provider=github&linked=true"


def test_oauth_callback_link_json_mode(client, monkeypatch):
    monkeypatch.setattr(
        oauth_external,
        "parse_oauth_state",
        lambda *_args, **_kwargs: oauth_external.OAuthState(
            provider="github",
            code_verifier="verifier",
            redirect_to_frontend=False,
            link_user_id=1,
        ),
    )
    monkeypatch.setattr(
        oauth_external,
        "complete_oauth_callback",
        lambda *_args, **_kwargs: oauth_external.OAuthCallbackResult(
            provider="github",
            redirect_to_frontend=False,
            linked=True,
        ),
    )

    response = client.get(
        "/api/v1/auth/oauth/github/callback",
        params={"state": "state-token", "code": "provider-code"},
    )

    assert response.status_code == 200
    assert response.json() == {"provider": "github", "linked": True}


def test_oauth_callback_redirect_mode_missing_token_returns_500(client, monkeypatch):
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
        "complete_oauth_callback",
        lambda *_args, **_kwargs: oauth_external.OAuthCallbackResult(
            provider="github",
            redirect_to_frontend=True,
            token=None,
            linked=False,
        ),
    )

    response = client.get(
        "/api/v1/auth/oauth/github/callback",
        params={"state": "state-token", "code": "provider-code"},
    )
    assert response.status_code == 500
    assert response.json()["error_code"] == "oauth_callback_invalid_response"


def test_oauth_callback_json_mode_missing_token_returns_500(client, monkeypatch):
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
        "complete_oauth_callback",
        lambda *_args, **_kwargs: oauth_external.OAuthCallbackResult(
            provider="github",
            redirect_to_frontend=False,
            token=None,
            linked=False,
        ),
    )

    response = client.get(
        "/api/v1/auth/oauth/github/callback",
        params={"state": "state-token", "code": "provider-code"},
    )
    assert response.status_code == 500
    assert response.json()["error_code"] == "oauth_callback_invalid_response"


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
        "complete_oauth_callback",
        lambda *_args, **_kwargs: oauth_external.OAuthCallbackResult(
            provider="github",
            redirect_to_frontend=False,
            token=token,
        ),
    )

    response = client.post(
        "/api/v1/auth/oauth/github/callback",
        data={"state": "state-token", "code": "provider-code"},
    )

    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"
