from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from app import models, oauth_external
from app.config import settings
from fastapi import HTTPException
from jose import JWTError
from starlette.requests import Request

pytestmark = pytest.mark.unit


class DummyResponse:
    def __init__(self, status_code: int, payload: Any = None, *, invalid_json: bool = False):
        self.status_code = status_code
        self._payload = payload
        self._invalid_json = invalid_json

    def json(self):
        if self._invalid_json:
            raise ValueError("invalid json")
        return self._payload


@pytest.fixture(autouse=True)
def reset_oauth_settings(monkeypatch):
    for provider in ["google", "microsoft", "apple", "facebook", "github"]:
        monkeypatch.setattr(settings, f"oauth_{provider}_client_id", None)
        monkeypatch.setattr(settings, f"oauth_{provider}_client_secret", None)
    monkeypatch.setattr(settings, "oauth_public_base_url", None)
    monkeypatch.setattr(settings, "oauth_state_expire_seconds", 300)
    monkeypatch.setattr(settings, "oauth_frontend_callback_url", "/")


@pytest.fixture
def fake_request() -> Request:
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "scheme": "http",
        "method": "GET",
        "path": "/api/v1/auth/oauth/google/start",
        "raw_path": b"/api/v1/auth/oauth/google/start",
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }
    return Request(scope)


def _enable_provider(monkeypatch, provider: str) -> None:
    monkeypatch.setattr(settings, f"oauth_{provider}_client_id", f"{provider}-client-id")
    monkeypatch.setattr(
        settings,
        f"oauth_{provider}_client_secret",
        f"{provider}-client-secret",
    )


def test_get_provider_rejects_unsupported():
    with pytest.raises(HTTPException) as exc_info:
        oauth_external.get_provider("not-real")
    assert exc_info.value.status_code == 404


def test_provider_credentials_rejects_unknown_provider():
    with pytest.raises(HTTPException) as exc_info:
        oauth_external._provider_credentials("unknown-provider")
    assert exc_info.value.status_code == 404


def test_get_provider_rejects_unconfigured():
    with pytest.raises(HTTPException) as exc_info:
        oauth_external.get_provider("google")
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["error_code"] == "oauth_provider_not_configured"


def test_list_enabled_providers(monkeypatch):
    _enable_provider(monkeypatch, "google")
    _enable_provider(monkeypatch, "github")
    providers = oauth_external.list_enabled_providers()
    assert {provider.provider for provider in providers} == {"google", "github"}


def test_build_and_parse_oauth_state_round_trip():
    state = oauth_external.build_oauth_state(
        provider="google",
        code_verifier="verifier",
        redirect_to_frontend=True,
    )
    parsed = oauth_external.parse_oauth_state(state, expected_provider="google")
    assert parsed.provider == "google"
    assert parsed.code_verifier == "verifier"
    assert parsed.redirect_to_frontend is True


def test_build_and_parse_oauth_state_with_link_user_id():
    state = oauth_external.build_oauth_state(
        provider="github",
        code_verifier="verifier",
        redirect_to_frontend=True,
        link_user_id=42,
    )
    parsed = oauth_external.parse_oauth_state(state, expected_provider="github")
    assert parsed.link_user_id == 42


def test_parse_oauth_state_rejects_invalid_token():
    with pytest.raises(HTTPException) as exc_info:
        oauth_external.parse_oauth_state("not-a-token", expected_provider="google")
    assert exc_info.value.status_code == 400


def test_parse_oauth_state_rejects_provider_mismatch():
    state = oauth_external.build_oauth_state(
        provider="google",
        code_verifier="verifier",
        redirect_to_frontend=True,
    )
    with pytest.raises(HTTPException) as exc_info:
        oauth_external.parse_oauth_state(state, expected_provider="github")
    assert exc_info.value.detail["error_code"] == "invalid_oauth_state"


def test_parse_oauth_state_rejects_wrong_token_type():
    token = oauth_external.jwt.encode(
        {
            "token_type": "not_oauth_state",
            "provider": "google",
            "code_verifier": "verifier",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        oauth_external.oauth2.SECRET_KEY,
        algorithm=oauth_external.oauth2.ALGORITHM,
    )
    with pytest.raises(HTTPException):
        oauth_external.parse_oauth_state(token, expected_provider="google")


def test_parse_oauth_state_rejects_missing_code_verifier(monkeypatch):
    token = oauth_external.jwt.encode(
        {
            "token_type": "oauth_state",
            "provider": "google",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        oauth_external.oauth2.SECRET_KEY,
        algorithm=oauth_external.oauth2.ALGORITHM,
    )
    with pytest.raises(HTTPException):
        oauth_external.parse_oauth_state(token, expected_provider="google")


def test_parse_oauth_state_rejects_invalid_link_user_id_type():
    token = oauth_external.jwt.encode(
        {
            "token_type": "oauth_state",
            "provider": "google",
            "code_verifier": "verifier",
            "link_user_id": "not-an-int",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        oauth_external.oauth2.SECRET_KEY,
        algorithm=oauth_external.oauth2.ALGORITHM,
    )
    with pytest.raises(HTTPException):
        oauth_external.parse_oauth_state(token, expected_provider="google")


def test_parse_oauth_state_rejects_non_positive_link_user_id():
    token = oauth_external.jwt.encode(
        {
            "token_type": "oauth_state",
            "provider": "google",
            "code_verifier": "verifier",
            "link_user_id": 0,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        oauth_external.oauth2.SECRET_KEY,
        algorithm=oauth_external.oauth2.ALGORITHM,
    )
    with pytest.raises(HTTPException):
        oauth_external.parse_oauth_state(token, expected_provider="google")


def test_build_authorization_url_google(monkeypatch, fake_request):
    _enable_provider(monkeypatch, "google")
    url = oauth_external.build_authorization_url(
        "google",
        fake_request,
        redirect_to_frontend=False,
    )
    parsed = urlparse(url)
    assert parsed.netloc == "accounts.google.com"
    query = parse_qs(parsed.query)
    assert query["client_id"][0] == "google-client-id"
    assert query["scope"][0] == "openid email profile"
    assert query["code_challenge_method"][0] == "S256"
    state_token = query["state"][0]
    state = oauth_external.parse_oauth_state(state_token, expected_provider="google")
    assert state.redirect_to_frontend is False
    assert state.link_user_id is None


def test_build_authorization_url_with_link_user_id(monkeypatch, fake_request):
    _enable_provider(monkeypatch, "github")
    url = oauth_external.build_authorization_url(
        "github",
        fake_request,
        redirect_to_frontend=True,
        link_user_id=123,
    )
    query = parse_qs(urlparse(url).query)
    state = oauth_external.parse_oauth_state(
        query["state"][0], expected_provider="github"
    )
    assert state.link_user_id == 123


def test_build_authorization_url_uses_public_base(monkeypatch, fake_request):
    _enable_provider(monkeypatch, "google")
    monkeypatch.setattr(settings, "oauth_public_base_url", "https://api.example.com")
    url = oauth_external.build_authorization_url(
        "google", fake_request, redirect_to_frontend=True
    )
    query = parse_qs(urlparse(url).query)
    assert query["redirect_uri"][0] == "https://api.example.com/api/v1/auth/oauth/google/callback"


def test_build_authorization_url_apple_sets_response_mode(monkeypatch, fake_request):
    _enable_provider(monkeypatch, "apple")
    url = oauth_external.build_authorization_url(
        "apple",
        fake_request,
        redirect_to_frontend=True,
    )
    query = parse_qs(urlparse(url).query)
    assert query["response_mode"][0] == "form_post"


def test_exchange_code_for_token_google_success(monkeypatch, fake_request):
    _enable_provider(monkeypatch, "google")

    captured: dict[str, Any] = {}

    def fake_post(url: str, *, data: dict[str, str], headers: dict[str, str], timeout: float):
        captured["url"] = url
        captured["data"] = data
        captured["headers"] = headers
        captured["timeout"] = timeout
        return DummyResponse(200, {"access_token": "token-123"})

    monkeypatch.setattr(oauth_external.httpx, "post", fake_post)
    payload = oauth_external._exchange_code_for_token(
        "google",
        fake_request,
        code="code-123",
        code_verifier="verifier-123",
    )
    assert payload["access_token"] == "token-123"
    assert captured["data"]["grant_type"] == "authorization_code"


def test_exchange_code_for_token_github_omits_grant_type(monkeypatch, fake_request):
    _enable_provider(monkeypatch, "github")

    captured: dict[str, Any] = {}

    def fake_post(url: str, *, data: dict[str, str], headers: dict[str, str], timeout: float):
        captured["data"] = data
        return DummyResponse(200, {"access_token": "token-123"})

    monkeypatch.setattr(oauth_external.httpx, "post", fake_post)
    oauth_external._exchange_code_for_token(
        "github",
        fake_request,
        code="code-123",
        code_verifier="verifier-123",
    )
    assert "grant_type" not in captured["data"]


def test_exchange_code_for_token_handles_network_error(monkeypatch, fake_request):
    _enable_provider(monkeypatch, "google")

    def fake_post(*_args, **_kwargs):
        raise httpx.HTTPError("boom")

    monkeypatch.setattr(oauth_external.httpx, "post", fake_post)
    with pytest.raises(HTTPException) as exc_info:
        oauth_external._exchange_code_for_token(
            "google",
            fake_request,
            code="code-123",
            code_verifier="verifier-123",
        )
    assert exc_info.value.status_code == 502


def test_exchange_code_for_token_handles_error_response(monkeypatch, fake_request):
    _enable_provider(monkeypatch, "google")

    def fake_post(*_args, **_kwargs):
        return DummyResponse(400, {"error": "invalid_grant"})

    monkeypatch.setattr(oauth_external.httpx, "post", fake_post)
    with pytest.raises(HTTPException) as exc_info:
        oauth_external._exchange_code_for_token(
            "google",
            fake_request,
            code="code-123",
            code_verifier="verifier-123",
        )
    assert exc_info.value.detail["error_code"] == "oauth_exchange_failed"


def test_exchange_code_for_token_rejects_missing_access_token(monkeypatch, fake_request):
    _enable_provider(monkeypatch, "google")

    def fake_post(*_args, **_kwargs):
        return DummyResponse(200, {"token_type": "bearer"})

    monkeypatch.setattr(oauth_external.httpx, "post", fake_post)
    with pytest.raises(HTTPException) as exc_info:
        oauth_external._exchange_code_for_token(
            "google",
            fake_request,
            code="code-123",
            code_verifier="verifier-123",
        )
    assert exc_info.value.status_code == 502


def test_exchange_code_for_token_handles_non_json_response(monkeypatch, fake_request):
    _enable_provider(monkeypatch, "google")

    def fake_post(*_args, **_kwargs):
        return DummyResponse(200, None, invalid_json=True)

    monkeypatch.setattr(oauth_external.httpx, "post", fake_post)
    with pytest.raises(HTTPException) as exc_info:
        oauth_external._exchange_code_for_token(
            "google",
            fake_request,
            code="code-123",
            code_verifier="verifier-123",
        )
    assert exc_info.value.status_code == 502


def test_fetch_json_success(monkeypatch):
    def fake_get(*_args, **_kwargs):
        return DummyResponse(200, {"hello": "world"})

    monkeypatch.setattr(oauth_external.httpx, "get", fake_get)
    payload = oauth_external._fetch_json("https://example.com", access_token="token")
    assert payload == {"hello": "world"}


def test_fetch_json_includes_custom_headers(monkeypatch):
    captured: dict[str, Any] = {}

    def fake_get(*_args, **kwargs):
        captured["headers"] = kwargs["headers"]
        return DummyResponse(200, {"ok": True})

    monkeypatch.setattr(oauth_external.httpx, "get", fake_get)
    payload = oauth_external._fetch_json(
        "https://example.com",
        access_token="token",
        headers={"X-Test": "yes"},
    )
    assert payload == {"ok": True}
    assert captured["headers"]["Authorization"] == "Bearer token"
    assert captured["headers"]["X-Test"] == "yes"


@pytest.mark.parametrize(
    "response",
    [
        DummyResponse(500, {"error": "boom"}),
        DummyResponse(200, None, invalid_json=True),
        DummyResponse(200, ["bad"]),
    ],
)
def test_fetch_json_rejects_invalid_responses(monkeypatch, response):
    def fake_get(*_args, **_kwargs):
        return response

    monkeypatch.setattr(oauth_external.httpx, "get", fake_get)
    with pytest.raises(HTTPException) as exc_info:
        oauth_external._fetch_json("https://example.com", access_token="token")
    assert exc_info.value.status_code == 502


def test_fetch_json_handles_network_error(monkeypatch):
    def fake_get(*_args, **_kwargs):
        raise httpx.HTTPError("network")

    monkeypatch.setattr(oauth_external.httpx, "get", fake_get)
    with pytest.raises(HTTPException) as exc_info:
        oauth_external._fetch_json("https://example.com", access_token="token")
    assert exc_info.value.status_code == 502


@pytest.mark.parametrize(
    "value,expected",
    [
        (True, True),
        (False, False),
        ("true", True),
        ("1", True),
        ("no", False),
        (1, True),
        (0, False),
        (None, False),
    ],
)
def test_to_bool(value, expected):
    assert oauth_external._to_bool(value) is expected


def test_get_identity_from_apple_success(monkeypatch):
    monkeypatch.setattr(
        oauth_external.jwt,
        "get_unverified_claims",
        lambda _token: {"sub": "apple-sub", "email": "apple@example.com", "email_verified": "true"},
    )
    identity = oauth_external._get_identity_from_apple({"id_token": "id-token"})
    assert identity.provider == "apple"
    assert identity.subject == "apple-sub"
    assert identity.email == "apple@example.com"
    assert identity.email_verified is True


@pytest.mark.parametrize(
    "payload,patcher",
    [
        ({}, None),
        ({"id_token": "id-token"}, lambda: (_ for _ in ()).throw(JWTError("bad"))),
        ({"id_token": "id-token"}, lambda: {"email": "missing-sub@example.com"}),
    ],
)
def test_get_identity_from_apple_error_cases(monkeypatch, payload, patcher):
    if patcher is not None:
        monkeypatch.setattr(oauth_external.jwt, "get_unverified_claims", lambda _token: patcher())
    with pytest.raises(HTTPException):
        oauth_external._get_identity_from_apple(payload)


def test_select_github_email_prefers_primary_verified(monkeypatch):
    def fake_get(*_args, **_kwargs):
        return DummyResponse(
            200,
            [
                {"email": "secondary@example.com", "verified": True, "primary": False},
                {"email": "primary@example.com", "verified": True, "primary": True},
            ],
        )

    monkeypatch.setattr(oauth_external.httpx, "get", fake_get)
    email, verified = oauth_external._select_github_email("token")
    assert email == "primary@example.com"
    assert verified is True


def test_select_github_email_handles_failure(monkeypatch):
    def fake_get(*_args, **_kwargs):
        raise httpx.HTTPError("nope")

    monkeypatch.setattr(oauth_external.httpx, "get", fake_get)
    email, verified = oauth_external._select_github_email("token")
    assert email is None
    assert verified is False


def test_select_github_email_handles_error_status(monkeypatch):
    monkeypatch.setattr(
        oauth_external.httpx,
        "get",
        lambda *_args, **_kwargs: DummyResponse(500, {"error": "boom"}),
    )
    email, verified = oauth_external._select_github_email("token")
    assert email is None
    assert verified is False


def test_select_github_email_handles_invalid_json(monkeypatch):
    monkeypatch.setattr(
        oauth_external.httpx,
        "get",
        lambda *_args, **_kwargs: DummyResponse(200, None, invalid_json=True),
    )
    email, verified = oauth_external._select_github_email("token")
    assert email is None
    assert verified is False


def test_select_github_email_handles_non_list_payload(monkeypatch):
    monkeypatch.setattr(
        oauth_external.httpx,
        "get",
        lambda *_args, **_kwargs: DummyResponse(200, {"not": "a-list"}),
    )
    email, verified = oauth_external._select_github_email("token")
    assert email is None
    assert verified is False


def test_select_github_email_uses_verified_fallback(monkeypatch):
    monkeypatch.setattr(
        oauth_external.httpx,
        "get",
        lambda *_args, **_kwargs: DummyResponse(
            200,
            [
                {"email": "unverified@example.com", "verified": False, "primary": True},
                {"email": "verified@example.com", "verified": True, "primary": False},
            ],
        ),
    )
    email, verified = oauth_external._select_github_email("token")
    assert email == "verified@example.com"
    assert verified is True


def test_select_github_email_primary_with_empty_email_returns_none(monkeypatch):
    monkeypatch.setattr(
        oauth_external.httpx,
        "get",
        lambda *_args, **_kwargs: DummyResponse(
            200,
            [
                {"email": "", "verified": True, "primary": True},
                {"email": "fallback@example.com", "verified": True, "primary": False},
            ],
        ),
    )
    email, verified = oauth_external._select_github_email("token")
    assert email is None
    assert verified is False


def test_select_github_email_returns_none_when_no_usable_verified_emails(monkeypatch):
    monkeypatch.setattr(
        oauth_external.httpx,
        "get",
        lambda *_args, **_kwargs: DummyResponse(
            200,
            [
                {"email": "", "verified": False, "primary": True},
                {"email": None, "verified": True, "primary": False},
            ],
        ),
    )
    email, verified = oauth_external._select_github_email("token")
    assert email is None
    assert verified is False


def test_select_github_email_returns_none_when_no_verified_candidates(monkeypatch):
    monkeypatch.setattr(
        oauth_external.httpx,
        "get",
        lambda *_args, **_kwargs: DummyResponse(
            200,
            [
                {"email": "first@example.com", "verified": False, "primary": True},
                {"email": "second@example.com", "verified": False, "primary": False},
            ],
        ),
    )
    email, verified = oauth_external._select_github_email("token")
    assert email is None
    assert verified is False


def test_identity_from_userinfo_variants():
    microsoft = oauth_external._identity_from_userinfo(
        provider="microsoft",
        payload={"sub": "abc", "preferred_username": "ms@example.com"},
    )
    assert microsoft.email == "ms@example.com"

    facebook = oauth_external._identity_from_userinfo(
        provider="facebook",
        payload={"id": "123", "email": "fb@example.com", "email_verified": False},
    )
    assert facebook.email_verified is True

    microsoft_no_preferred = oauth_external._identity_from_userinfo(
        provider="microsoft",
        payload={"sub": "abc"},
    )
    assert microsoft_no_preferred.email is None


def test_identity_from_userinfo_requires_subject():
    with pytest.raises(HTTPException):
        oauth_external._identity_from_userinfo(provider="google", payload={})


@pytest.mark.parametrize("provider", ["google", "microsoft", "facebook"])
def test_fetch_external_identity_generic_providers(monkeypatch, provider):
    _enable_provider(monkeypatch, provider)
    monkeypatch.setattr(
        oauth_external,
        "_fetch_json",
        lambda *_args, **_kwargs: {
            "sub": "sub-123",
            "id": "123",
            "email": "user@example.com",
            "email_verified": True,
        },
    )
    token_payload = {"access_token": "token"}
    identity = oauth_external.fetch_external_identity(provider, token_payload)
    assert identity.email == "user@example.com"


def test_fetch_external_identity_github_fallback_email(monkeypatch):
    _enable_provider(monkeypatch, "github")
    monkeypatch.setattr(
        oauth_external,
        "_fetch_json",
        lambda *_args, **_kwargs: {"id": 1234},
    )
    monkeypatch.setattr(
        oauth_external,
        "_select_github_email",
        lambda _token: ("gh@example.com", True),
    )
    identity = oauth_external.fetch_external_identity("github", {"access_token": "token"})
    assert identity.subject == "1234"
    assert identity.email == "gh@example.com"


def test_fetch_external_identity_github_keeps_primary_email(monkeypatch):
    _enable_provider(monkeypatch, "github")
    monkeypatch.setattr(
        oauth_external,
        "_fetch_json",
        lambda *_args, **_kwargs: {"id": 5678, "email": "present@example.com"},
    )
    identity = oauth_external.fetch_external_identity("github", {"access_token": "token"})
    assert identity.email == "present@example.com"


def test_fetch_external_identity_apple(monkeypatch):
    _enable_provider(monkeypatch, "apple")
    monkeypatch.setattr(
        oauth_external,
        "_get_identity_from_apple",
        lambda payload: oauth_external.ExternalIdentity(
            provider="apple",
            subject="apple-sub",
            email="apple@example.com",
            email_verified=True,
        ),
    )
    identity = oauth_external.fetch_external_identity("apple", {"access_token": "token"})
    assert identity.subject == "apple-sub"


def test_fetch_external_identity_rejects_missing_profile_endpoint(monkeypatch):
    _enable_provider(monkeypatch, "google")
    monkeypatch.setitem(
        oauth_external._PROVIDERS,
        "google",
        oauth_external.OAuthProviderConfig(
            provider="google",
            display_name="Google",
            authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
            token_url="https://oauth2.googleapis.com/token",
            scopes=("openid", "email", "profile"),
            userinfo_url=None,
        ),
    )
    with pytest.raises(HTTPException) as exc_info:
        oauth_external.fetch_external_identity("google", {"access_token": "token"})
    assert exc_info.value.status_code == 502


@pytest.mark.integration
def test_find_or_create_user_for_identity_creates_user_and_account(session):
    identity = oauth_external.ExternalIdentity(
        provider="google",
        subject="subject-1",
        email="oauth-new@example.com",
        email_verified=True,
    )
    user = oauth_external._find_or_create_user_for_identity(session, identity)
    session.commit()

    assert user.email == "oauth-new@example.com"
    account = (
        session.query(models.OAuthAccount)
        .filter(models.OAuthAccount.provider_subject == "subject-1")
        .first()
    )
    assert account is not None
    assert account.user_id == user.id


@pytest.mark.integration
def test_find_or_create_user_for_identity_links_existing_email_user(session):
    user = models.User(email="existing@example.com", password="hashed")
    session.add(user)
    session.commit()

    identity = oauth_external.ExternalIdentity(
        provider="github",
        subject="gh-1",
        email="existing@example.com",
        email_verified=True,
    )
    resolved = oauth_external._find_or_create_user_for_identity(session, identity)
    session.commit()

    assert resolved.id == user.id
    account = (
        session.query(models.OAuthAccount)
        .filter(models.OAuthAccount.provider == "github")
        .first()
    )
    assert account is not None
    assert account.user_id == user.id


@pytest.mark.integration
def test_find_or_create_user_for_identity_uses_existing_account_and_updates(session):
    user = models.User(email="linked@example.com", password="hashed")
    session.add(user)
    session.flush()

    old_login = datetime.now(timezone.utc) - timedelta(days=2)
    account = models.OAuthAccount(
        user_id=int(user.id),
        provider="google",
        provider_subject="subject-existing",
        provider_email="old@example.com",
        last_login_at=old_login,
    )
    session.add(account)
    session.commit()

    identity = oauth_external.ExternalIdentity(
        provider="google",
        subject="subject-existing",
        email="new@example.com",
        email_verified=True,
    )
    resolved = oauth_external._find_or_create_user_for_identity(session, identity)
    session.commit()

    assert resolved.id == user.id
    updated = (
        session.query(models.OAuthAccount)
        .filter(models.OAuthAccount.provider_subject == "subject-existing")
        .first()
    )
    assert updated is not None
    assert updated.provider_email == "new@example.com"


@pytest.mark.integration
def test_find_or_create_user_for_identity_existing_account_without_email(session):
    user = models.User(email="linked-no-email@example.com", password="hashed")
    session.add(user)
    session.flush()
    account = models.OAuthAccount(
        user_id=int(user.id),
        provider="facebook",
        provider_subject="subject-no-email",
        provider_email="previous@example.com",
    )
    session.add(account)
    session.commit()

    identity = oauth_external.ExternalIdentity(
        provider="facebook",
        subject="subject-no-email",
        email=None,
        email_verified=False,
    )
    resolved = oauth_external._find_or_create_user_for_identity(session, identity)
    session.commit()
    assert resolved.id == user.id


@pytest.mark.integration
def test_find_or_create_user_for_identity_requires_email_for_new_account(session):
    identity = oauth_external.ExternalIdentity(
        provider="google",
        subject="missing-email-subject",
        email=None,
        email_verified=False,
    )
    with pytest.raises(HTTPException) as exc_info:
        oauth_external._find_or_create_user_for_identity(session, identity)
    assert exc_info.value.status_code == 422


@pytest.mark.integration
def test_link_identity_to_existing_user_user_not_found(session):
    identity = oauth_external.ExternalIdentity(
        provider="github",
        subject="sub-1",
        email="link@example.com",
        email_verified=True,
    )
    with pytest.raises(HTTPException) as exc_info:
        oauth_external._link_identity_to_existing_user(
            session, user_id=999_999, identity=identity
        )
    assert exc_info.value.status_code == 404


@pytest.mark.integration
def test_link_identity_to_existing_user_conflict_other_user(session):
    user_a = models.User(email="a@example.com", password="hashed")
    user_b = models.User(email="b@example.com", password="hashed")
    session.add_all([user_a, user_b])
    session.flush()
    session.add(
        models.OAuthAccount(
            user_id=int(user_a.id),
            provider="github",
            provider_subject="subject-1",
            provider_email="a@example.com",
        )
    )
    session.commit()

    identity = oauth_external.ExternalIdentity(
        provider="github",
        subject="subject-1",
        email="b@example.com",
        email_verified=True,
    )
    with pytest.raises(HTTPException) as exc_info:
        oauth_external._link_identity_to_existing_user(
            session, user_id=int(user_b.id), identity=identity
        )
    assert exc_info.value.status_code == 409


@pytest.mark.integration
def test_link_identity_to_existing_user_provider_already_linked_different_subject(session):
    user = models.User(email="existing-link@example.com", password="hashed")
    session.add(user)
    session.flush()
    session.add(
        models.OAuthAccount(
            user_id=int(user.id),
            provider="github",
            provider_subject="subject-a",
            provider_email="existing-link@example.com",
        )
    )
    session.commit()

    identity = oauth_external.ExternalIdentity(
        provider="github",
        subject="subject-b",
        email="existing-link@example.com",
        email_verified=True,
    )
    with pytest.raises(HTTPException) as exc_info:
        oauth_external._link_identity_to_existing_user(
            session, user_id=int(user.id), identity=identity
        )
    assert exc_info.value.status_code == 409


@pytest.mark.integration
def test_link_identity_to_existing_user_idempotent_update(session):
    user = models.User(email="idempotent@example.com", password="hashed")
    session.add(user)
    session.flush()
    session.add(
        models.OAuthAccount(
            user_id=int(user.id),
            provider="google",
            provider_subject="subject-1",
            provider_email="old@example.com",
        )
    )
    session.commit()

    identity = oauth_external.ExternalIdentity(
        provider="google",
        subject="subject-1",
        email="new@example.com",
        email_verified=True,
    )
    oauth_external._link_identity_to_existing_user(
        session, user_id=int(user.id), identity=identity
    )
    session.commit()

    account = (
        session.query(models.OAuthAccount)
        .filter(models.OAuthAccount.user_id == user.id, models.OAuthAccount.provider == "google")
        .first()
    )
    assert account is not None
    assert account.provider_email == "new@example.com"


@pytest.mark.integration
def test_link_identity_to_existing_user_idempotent_without_new_email(session):
    user = models.User(email="idempotent-no-email@example.com", password="hashed")
    session.add(user)
    session.flush()
    session.add(
        models.OAuthAccount(
            user_id=int(user.id),
            provider="google",
            provider_subject="subject-1",
            provider_email="existing@example.com",
        )
    )
    session.commit()

    identity = oauth_external.ExternalIdentity(
        provider="google",
        subject="subject-1",
        email=None,
        email_verified=False,
    )
    oauth_external._link_identity_to_existing_user(
        session, user_id=int(user.id), identity=identity
    )
    session.commit()

    account = (
        session.query(models.OAuthAccount)
        .filter(models.OAuthAccount.user_id == user.id, models.OAuthAccount.provider == "google")
        .first()
    )
    assert account is not None
    assert account.provider_email == "existing@example.com"


@pytest.mark.integration
def test_link_identity_to_existing_user_creates_new_account(session):
    user = models.User(email="new-link@example.com", password="hashed")
    session.add(user)
    session.commit()

    identity = oauth_external.ExternalIdentity(
        provider="facebook",
        subject="fb-subject",
        email="new-link@example.com",
        email_verified=True,
    )
    oauth_external._link_identity_to_existing_user(
        session, user_id=int(user.id), identity=identity
    )
    session.commit()

    account = (
        session.query(models.OAuthAccount)
        .filter(models.OAuthAccount.user_id == user.id, models.OAuthAccount.provider == "facebook")
        .first()
    )
    assert account is not None
    assert account.provider_subject == "fb-subject"


@pytest.mark.integration
def test_complete_oauth_callback_returns_token_result(session, monkeypatch, fake_request):
    user = models.User(email="callback@example.com", password="hashed")
    session.add(user)
    session.commit()

    monkeypatch.setattr(
        oauth_external,
        "_exchange_code_for_token",
        lambda *_args, **_kwargs: {"access_token": "oauth-provider-token"},
    )
    monkeypatch.setattr(
        oauth_external,
        "fetch_external_identity",
        lambda *_args, **_kwargs: oauth_external.ExternalIdentity(
            provider="google",
            subject="subject-123",
            email="callback@example.com",
            email_verified=True,
        ),
    )

    result = oauth_external.complete_oauth_callback(
        session,
        fake_request,
        provider="google",
        code="code-123",
        state=oauth_external.OAuthState(
            provider="google",
            code_verifier="verifier",
            redirect_to_frontend=True,
        ),
    )
    assert result.redirect_to_frontend is True
    assert result.linked is False
    assert result.token is not None
    assert result.token.access_token


@pytest.mark.integration
def test_complete_oauth_callback_link_mode(session, monkeypatch, fake_request):
    user = models.User(email="link-callback@example.com", password="hashed")
    session.add(user)
    session.commit()

    monkeypatch.setattr(
        oauth_external,
        "_exchange_code_for_token",
        lambda *_args, **_kwargs: {"access_token": "oauth-provider-token"},
    )
    monkeypatch.setattr(
        oauth_external,
        "fetch_external_identity",
        lambda *_args, **_kwargs: oauth_external.ExternalIdentity(
            provider="github",
            subject="subject-link",
            email="link-callback@example.com",
            email_verified=True,
        ),
    )

    result = oauth_external.complete_oauth_callback(
        session,
        fake_request,
        provider="github",
        code="code-123",
        state=oauth_external.OAuthState(
            provider="github",
            code_verifier="verifier",
            redirect_to_frontend=False,
            link_user_id=int(user.id),
        ),
    )
    assert result.linked is True
    assert result.token is None


def test_build_frontend_redirect_helpers():
    token = oauth_external.schemas.Token(
        access_token="access",
        token_type="bearer",
        refresh_token="refresh",
    )
    success = oauth_external.build_frontend_success_redirect("github", token)
    error = oauth_external.build_frontend_error_redirect("github", error="denied")

    assert success.startswith("/#")
    assert "access_token=access" in success
    assert "provider=github" in success
    assert error == "/#provider=github&error=denied"


def test_build_frontend_success_redirect_without_refresh_token():
    token = oauth_external.schemas.Token(access_token="access", token_type="bearer")
    success = oauth_external.build_frontend_success_redirect("google", token)
    assert "refresh_token" not in success


def test_build_frontend_link_redirect():
    redirect = oauth_external.build_frontend_link_redirect("github")
    assert redirect == "/#provider=github&linked=true"
