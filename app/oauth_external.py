from __future__ import annotations

import base64
import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException, Request, status
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from . import models, oauth2, schemas, utils
from .config import settings
from .outbox import enqueue_outbox_event

_OAUTH_STATE_TOKEN_TYPE = "oauth_state"


@dataclass(frozen=True)
class OAuthProviderConfig:
    provider: str
    display_name: str
    authorize_url: str
    token_url: str
    scopes: tuple[str, ...]
    userinfo_url: str | None
    userinfo_params: dict[str, str] | None = None
    authorize_params: dict[str, str] | None = None


@dataclass(frozen=True)
class OAuthState:
    provider: str
    code_verifier: str
    redirect_to_frontend: bool
    link_user_id: int | None = None


@dataclass(frozen=True)
class ExternalIdentity:
    provider: str
    subject: str
    email: str | None
    email_verified: bool


@dataclass(frozen=True)
class OAuthCallbackResult:
    provider: str
    redirect_to_frontend: bool
    token: schemas.Token | None = None
    linked: bool = False


_PROVIDERS: dict[str, OAuthProviderConfig] = {
    "google": OAuthProviderConfig(
        provider="google",
        display_name="Google",
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",
        scopes=("openid", "email", "profile"),
        userinfo_url="https://openidconnect.googleapis.com/v1/userinfo",
    ),
    "microsoft": OAuthProviderConfig(
        provider="microsoft",
        display_name="Microsoft",
        authorize_url="https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        token_url="https://login.microsoftonline.com/common/oauth2/v2.0/token",
        scopes=("openid", "profile", "email"),
        userinfo_url="https://graph.microsoft.com/oidc/userinfo",
    ),
    "apple": OAuthProviderConfig(
        provider="apple",
        display_name="Apple",
        authorize_url="https://appleid.apple.com/auth/authorize",
        token_url="https://appleid.apple.com/auth/token",
        scopes=("openid", "email", "name"),
        userinfo_url=None,
        authorize_params={"response_mode": "form_post"},
    ),
    "facebook": OAuthProviderConfig(
        provider="facebook",
        display_name="Facebook",
        authorize_url="https://www.facebook.com/v19.0/dialog/oauth",
        token_url="https://graph.facebook.com/v19.0/oauth/access_token",
        scopes=("email", "public_profile"),
        userinfo_url="https://graph.facebook.com/me",
        userinfo_params={"fields": "id,name,email"},
    ),
    "github": OAuthProviderConfig(
        provider="github",
        display_name="GitHub",
        authorize_url="https://github.com/login/oauth/authorize",
        token_url="https://github.com/login/oauth/access_token",
        scopes=("read:user", "user:email"),
        userinfo_url="https://api.github.com/user",
    ),
}

_PROVIDER_CREDENTIAL_ATTRS: dict[str, tuple[str, str]] = {
    "google": ("oauth_google_client_id", "oauth_google_client_secret"),
    "microsoft": ("oauth_microsoft_client_id", "oauth_microsoft_client_secret"),
    "apple": ("oauth_apple_client_id", "oauth_apple_client_secret"),
    "facebook": ("oauth_facebook_client_id", "oauth_facebook_client_secret"),
    "github": ("oauth_github_client_id", "oauth_github_client_secret"),
}


def _oauth_error(
    detail: str,
    *,
    error_code: str,
    status_code: int = status.HTTP_400_BAD_REQUEST,
) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"detail": detail, "error_code": error_code},
    )


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _provider_credentials(provider: str) -> tuple[str, str]:
    attrs = _PROVIDER_CREDENTIAL_ATTRS.get(provider)
    if attrs is None:
        raise _oauth_error(
            f"Unsupported OAuth provider: {provider}",
            error_code="oauth_provider_unsupported",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    client_id = getattr(settings, attrs[0], None)
    client_secret = getattr(settings, attrs[1], None)
    if not client_id or not client_secret:
        raise _oauth_error(
            f"OAuth provider '{provider}' is not configured",
            error_code="oauth_provider_not_configured",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return str(client_id), str(client_secret)


def get_provider(provider: str) -> OAuthProviderConfig:
    config = _PROVIDERS.get(provider)
    if config is None:
        raise _oauth_error(
            f"Unsupported OAuth provider: {provider}",
            error_code="oauth_provider_unsupported",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    _provider_credentials(provider)
    return config


def list_enabled_providers() -> list[OAuthProviderConfig]:
    enabled: list[OAuthProviderConfig] = []
    for provider, config in _PROVIDERS.items():
        try:
            _provider_credentials(provider)
        except HTTPException:
            continue
        enabled.append(config)
    return enabled


def _callback_url(request: Request, provider: str) -> str:
    base = settings.oauth_public_base_url
    if base:
        normalized = str(base).rstrip("/")
    else:
        normalized = str(request.base_url).rstrip("/")
    return f"{normalized}/api/v1/auth/oauth/{provider}/callback"


def _build_code_verifier() -> str:
    return secrets.token_urlsafe(64)


def _build_code_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def build_oauth_state(
    *,
    provider: str,
    code_verifier: str,
    redirect_to_frontend: bool,
    link_user_id: int | None = None,
) -> str:
    payload = {
        "token_type": _OAUTH_STATE_TOKEN_TYPE,
        "provider": provider,
        "code_verifier": code_verifier,
        "redirect_to_frontend": redirect_to_frontend,
        "jti": uuid.uuid4().hex,
        "exp": _now_utc() + timedelta(seconds=settings.oauth_state_expire_seconds),
    }
    if link_user_id is not None:
        payload["link_user_id"] = int(link_user_id)
    return jwt.encode(payload, oauth2.SECRET_KEY, algorithm=oauth2.ALGORITHM)


def parse_oauth_state(state_token: str, *, expected_provider: str) -> OAuthState:
    try:
        payload = jwt.decode(
            state_token,
            oauth2.SECRET_KEY,
            algorithms=[oauth2.ALGORITHM],
        )
    except JWTError:
        raise _oauth_error("Invalid OAuth state", error_code="invalid_oauth_state")

    if payload.get("token_type") != _OAUTH_STATE_TOKEN_TYPE:
        raise _oauth_error("Invalid OAuth state", error_code="invalid_oauth_state")

    provider = payload.get("provider")
    if provider != expected_provider:
        raise _oauth_error("Invalid OAuth provider state", error_code="invalid_oauth_state")

    code_verifier = payload.get("code_verifier")
    if not isinstance(code_verifier, str) or not code_verifier:
        raise _oauth_error("Invalid OAuth state", error_code="invalid_oauth_state")

    redirect_to_frontend = bool(payload.get("redirect_to_frontend", True))
    raw_link_user_id = payload.get("link_user_id")
    link_user_id: int | None = None
    if raw_link_user_id is not None:
        try:
            link_user_id = int(raw_link_user_id)
        except (TypeError, ValueError):
            raise _oauth_error("Invalid OAuth state", error_code="invalid_oauth_state")
        if link_user_id <= 0:
            raise _oauth_error("Invalid OAuth state", error_code="invalid_oauth_state")
    return OAuthState(
        provider=provider,
        code_verifier=code_verifier,
        redirect_to_frontend=redirect_to_frontend,
        link_user_id=link_user_id,
    )


def build_authorization_url(
    provider: str,
    request: Request,
    *,
    redirect_to_frontend: bool,
    link_user_id: int | None = None,
) -> str:
    config = get_provider(provider)
    client_id, _ = _provider_credentials(provider)
    callback_url = _callback_url(request, provider)
    code_verifier = _build_code_verifier()
    code_challenge = _build_code_challenge(code_verifier)
    state = build_oauth_state(
        provider=provider,
        code_verifier=code_verifier,
        redirect_to_frontend=redirect_to_frontend,
        link_user_id=link_user_id,
    )

    params: dict[str, str] = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": callback_url,
        "scope": " ".join(config.scopes),
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    if config.authorize_params:
        params.update(config.authorize_params)
    return f"{config.authorize_url}?{urlencode(params)}"


def _exchange_code_for_token(
    provider: str, request: Request, *, code: str, code_verifier: str
) -> dict[str, Any]:
    config = get_provider(provider)
    client_id, client_secret = _provider_credentials(provider)
    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "redirect_uri": _callback_url(request, provider),
        "code_verifier": code_verifier,
    }
    if provider != "github":
        payload["grant_type"] = "authorization_code"

    headers = {"Accept": "application/json"}
    if provider == "github":
        headers["X-GitHub-Api-Version"] = "2022-11-28"

    try:
        response = httpx.post(
            config.token_url,
            data=payload,
            headers=headers,
            timeout=10.0,
        )
    except httpx.HTTPError:
        raise _oauth_error(
            "Could not reach OAuth provider",
            error_code="oauth_provider_unreachable",
            status_code=status.HTTP_502_BAD_GATEWAY,
        )

    try:
        token_payload = response.json()
    except ValueError:
        token_payload = {}

    if response.status_code >= 400 or "error" in token_payload:
        message = str(token_payload.get("error_description") or token_payload.get("error") or "OAuth code exchange failed")
        raise _oauth_error(message, error_code="oauth_exchange_failed")

    access_token = token_payload.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise _oauth_error(
            "OAuth provider did not return an access token",
            error_code="oauth_invalid_token_response",
            status_code=status.HTTP_502_BAD_GATEWAY,
        )

    return token_payload


def _fetch_json(
    url: str,
    *,
    access_token: str,
    params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    request_headers = {"Authorization": f"Bearer {access_token}"}
    if headers:
        request_headers.update(headers)
    try:
        response = httpx.get(
            url,
            params=params,
            headers=request_headers,
            timeout=10.0,
        )
    except httpx.HTTPError:
        raise _oauth_error(
            "Could not fetch OAuth profile",
            error_code="oauth_profile_fetch_failed",
            status_code=status.HTTP_502_BAD_GATEWAY,
        )

    if response.status_code >= 400:
        raise _oauth_error(
            "OAuth profile lookup failed",
            error_code="oauth_profile_fetch_failed",
            status_code=status.HTTP_502_BAD_GATEWAY,
        )

    try:
        payload = response.json()
    except ValueError:
        raise _oauth_error(
            "OAuth profile response was invalid",
            error_code="oauth_profile_fetch_failed",
            status_code=status.HTTP_502_BAD_GATEWAY,
        )

    if not isinstance(payload, dict):
        raise _oauth_error(
            "OAuth profile response was invalid",
            error_code="oauth_profile_fetch_failed",
            status_code=status.HTTP_502_BAD_GATEWAY,
        )
    return payload


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"true", "1", "yes"}
    if isinstance(value, int):
        return value != 0
    return False


def _get_identity_from_apple(token_payload: dict[str, Any]) -> ExternalIdentity:
    id_token = token_payload.get("id_token")
    if not isinstance(id_token, str) or not id_token:
        raise _oauth_error(
            "Apple OAuth response did not include id_token",
            error_code="oauth_profile_fetch_failed",
            status_code=status.HTTP_502_BAD_GATEWAY,
        )
    try:
        claims = jwt.get_unverified_claims(id_token)
    except JWTError:
        raise _oauth_error(
            "Apple OAuth id_token was invalid",
            error_code="oauth_profile_fetch_failed",
            status_code=status.HTTP_502_BAD_GATEWAY,
        )

    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject:
        raise _oauth_error(
            "Apple OAuth identity did not include subject",
            error_code="oauth_profile_fetch_failed",
            status_code=status.HTTP_502_BAD_GATEWAY,
        )
    email = claims.get("email")
    return ExternalIdentity(
        provider="apple",
        subject=subject,
        email=str(email) if isinstance(email, str) and email else None,
        email_verified=_to_bool(claims.get("email_verified")),
    )


def _select_github_email(access_token: str) -> tuple[str | None, bool]:
    try:
        response = httpx.get(
            "https://api.github.com/user/emails",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=10.0,
        )
    except httpx.HTTPError:
        return None, False

    if response.status_code >= 400:
        return None, False
    try:
        payload = response.json()
    except ValueError:
        return None, False

    if not isinstance(payload, list):
        return None, False
    candidates = [item for item in payload if isinstance(item, dict)]
    primary_verified = next(
        (
            item
            for item in candidates
            if _to_bool(item.get("verified")) and _to_bool(item.get("primary"))
        ),
        None,
    )
    if primary_verified is not None:
        email = primary_verified.get("email")
        if isinstance(email, str) and email:
            return email, True

    verified = next((item for item in candidates if _to_bool(item.get("verified"))), None)
    if verified is not None:
        email = verified.get("email")
        if isinstance(email, str) and email:
            return email, True
    return None, False


def _identity_from_userinfo(
    *,
    provider: str,
    payload: dict[str, Any],
) -> ExternalIdentity:
    raw_subject = payload.get("sub") if provider in {"google", "microsoft"} else payload.get("id")
    subject = str(raw_subject) if raw_subject is not None else ""
    if not subject:
        raise _oauth_error(
            "OAuth profile did not include subject",
            error_code="oauth_profile_fetch_failed",
            status_code=status.HTTP_502_BAD_GATEWAY,
        )

    email = payload.get("email")
    resolved_email = str(email) if isinstance(email, str) and email else None
    if provider == "microsoft" and not resolved_email:
        preferred = payload.get("preferred_username")
        if isinstance(preferred, str) and preferred:
            resolved_email = preferred

    email_verified = _to_bool(payload.get("email_verified"))
    if provider == "facebook" and resolved_email:
        email_verified = True

    return ExternalIdentity(
        provider=provider,
        subject=subject,
        email=resolved_email,
        email_verified=email_verified,
    )


def fetch_external_identity(provider: str, token_payload: dict[str, Any]) -> ExternalIdentity:
    access_token = token_payload["access_token"]
    if provider == "apple":
        return _get_identity_from_apple(token_payload)
    if provider == "github":
        user = _fetch_json(
            "https://api.github.com/user",
            access_token=access_token,
            headers={
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        identity = _identity_from_userinfo(provider="github", payload=user)
        if identity.email:
            return identity
        email, verified = _select_github_email(access_token)
        return ExternalIdentity(
            provider=identity.provider,
            subject=identity.subject,
            email=email,
            email_verified=verified,
        )

    config = get_provider(provider)
    if not config.userinfo_url:
        raise _oauth_error(
            "OAuth provider profile endpoint is not configured",
            error_code="oauth_profile_fetch_failed",
            status_code=status.HTTP_502_BAD_GATEWAY,
        )
    userinfo = _fetch_json(
        config.userinfo_url,
        access_token=access_token,
        params=config.userinfo_params,
    )
    return _identity_from_userinfo(provider=provider, payload=userinfo)


def _find_or_create_user_for_identity(db: Session, identity: ExternalIdentity) -> models.User:
    account = (
        db.query(models.OAuthAccount)
        .filter(
            models.OAuthAccount.provider == identity.provider,
            models.OAuthAccount.provider_subject == identity.subject,
        )
        .first()
    )
    now = _now_utc()
    if account is not None:
        account.last_login_at = now  # type: ignore[assignment]
        if identity.email:
            account.provider_email = identity.email  # type: ignore[assignment]
        return account.user

    if not identity.email:
        raise _oauth_error(
            "OAuth provider did not return an email address",
            error_code="oauth_email_required",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    user = db.query(models.User).filter(models.User.email == identity.email).first()
    if user is None:
        user = models.User(
            email=identity.email,
            password=utils.hash(secrets.token_urlsafe(48)),
        )
        db.add(user)
        db.flush()
        enqueue_outbox_event(
            db,
            topic="user.created",
            payload={"user_id": user.id, "email": user.email},
        )

    oauth_account = models.OAuthAccount(
        user_id=int(user.id),
        provider=identity.provider,
        provider_subject=identity.subject,
        provider_email=identity.email,
        last_login_at=now,
    )
    db.add(oauth_account)
    return user


def _link_identity_to_existing_user(
    db: Session,
    *,
    user_id: int,
    identity: ExternalIdentity,
) -> None:
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None:
        raise _oauth_error(
            "User does not exist",
            error_code="oauth_link_user_not_found",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    existing_subject_account = (
        db.query(models.OAuthAccount)
        .filter(
            models.OAuthAccount.provider == identity.provider,
            models.OAuthAccount.provider_subject == identity.subject,
        )
        .first()
    )
    if existing_subject_account is not None and int(existing_subject_account.user_id) != int(
        user.id
    ):
        raise _oauth_error(
            "OAuth identity is already linked to another account",
            error_code="oauth_identity_already_linked",
            status_code=status.HTTP_409_CONFLICT,
        )

    existing_provider_for_user = (
        db.query(models.OAuthAccount)
        .filter(
            models.OAuthAccount.user_id == user.id,
            models.OAuthAccount.provider == identity.provider,
        )
        .first()
    )
    now = _now_utc()
    if existing_provider_for_user is not None:
        if existing_provider_for_user.provider_subject != identity.subject:
            raise _oauth_error(
                "Provider is already linked to this account with a different identity",
                error_code="oauth_provider_already_linked",
                status_code=status.HTTP_409_CONFLICT,
            )
        existing_provider_for_user.last_login_at = now  # type: ignore[assignment]
        if identity.email:
            existing_provider_for_user.provider_email = identity.email  # type: ignore[assignment]
        return

    db.add(
        models.OAuthAccount(
            user_id=int(user.id),
            provider=identity.provider,
            provider_subject=identity.subject,
            provider_email=identity.email,
            last_login_at=now,
        )
    )


def complete_oauth_callback(
    db: Session,
    request: Request,
    *,
    provider: str,
    code: str,
    state: OAuthState,
) -> OAuthCallbackResult:
    token_payload = _exchange_code_for_token(
        provider,
        request,
        code=code,
        code_verifier=state.code_verifier,
    )
    identity = fetch_external_identity(provider, token_payload)

    if state.link_user_id is not None:
        _link_identity_to_existing_user(
            db,
            user_id=state.link_user_id,
            identity=identity,
        )
        db.commit()
        return OAuthCallbackResult(
            provider=provider,
            redirect_to_frontend=state.redirect_to_frontend,
            linked=True,
        )

    user = _find_or_create_user_for_identity(db, identity)
    db.flush()
    token_pair = oauth2.issue_token_pair(db, int(user.id))
    return OAuthCallbackResult(
        provider=provider,
        redirect_to_frontend=state.redirect_to_frontend,
        token=token_pair,
    )


def build_frontend_success_redirect(provider: str, token: schemas.Token) -> str:
    target = settings.oauth_frontend_callback_url or "/"
    params = {
        "provider": provider,
        "access_token": token.access_token,
        "token_type": token.token_type,
    }
    if token.refresh_token:
        params["refresh_token"] = token.refresh_token
    return f"{target}#{urlencode(params)}"


def build_frontend_link_redirect(provider: str) -> str:
    target = settings.oauth_frontend_callback_url or "/"
    params = {"provider": provider, "linked": "true"}
    return f"{target}#{urlencode(params)}"


def build_frontend_error_redirect(provider: str, *, error: str) -> str:
    target = settings.oauth_frontend_callback_url or "/"
    params = {"provider": provider, "error": error}
    return f"{target}#{urlencode(params)}"
