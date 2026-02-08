from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from fastapi.security.oauth2 import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from .. import database, models, oauth2, oauth_external, schemas, utils
from ..rate_limit import rate_limit_dependency

router = APIRouter(tags=["Authentication"])


@router.post("/login", response_model=schemas.Token)
def login(
    _: None = rate_limit_dependency("auth_login"),
    user_credentials: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(database.get_db),
):
    user = (
        db.query(models.User)
        .filter(models.User.email == user_credentials.username)
        .first()
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid Credentials"
        )

    if not utils.verify(user_credentials.password, user.password):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid Credentials"
        )

    return oauth2.issue_token_pair(db, int(user.id))


@router.post("/auth/refresh", response_model=schemas.Token)
def refresh(
    payload: schemas.RefreshTokenRequest,
    _: None = rate_limit_dependency("auth_login"),
    db: Session = Depends(database.get_db),
):
    return oauth2.rotate_refresh_token(db, payload.refresh_token)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    payload: schemas.RefreshTokenRequest,
    _: None = rate_limit_dependency("auth_login"),
    db: Session = Depends(database.get_db),
):
    oauth2.revoke_refresh_token(db, payload.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/auth/oauth/providers", response_model=schemas.OAuthProvidersResponse)
def oauth_providers():
    providers = [
        schemas.OAuthProvider(
            provider=provider.provider,
            display_name=provider.display_name,
            start_url=f"/api/v1/auth/oauth/{provider.provider}/start",
        )
        for provider in oauth_external.list_enabled_providers()
    ]
    return schemas.OAuthProvidersResponse(providers=providers)


def _oauth_error_message(error: Optional[str], error_description: Optional[str]) -> str:
    if error_description:
        return error_description
    if error:
        return error
    return "OAuth authentication failed"


async def _handle_oauth_callback(
    provider: str,
    request: Request,
    *,
    state: Optional[str],
    code: Optional[str],
    error: Optional[str],
    error_description: Optional[str],
    db: Session,
) -> Any:
    if not state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "detail": "OAuth callback is missing state",
                "error_code": "invalid_oauth_state",
            },
        )

    parsed_state = oauth_external.parse_oauth_state(state, expected_provider=provider)
    if error or error_description:
        message = _oauth_error_message(error, error_description)
        if parsed_state.redirect_to_frontend:
            redirect_url = oauth_external.build_frontend_error_redirect(
                provider, error=message
            )
            return RedirectResponse(redirect_url, status_code=status.HTTP_302_FOUND)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"detail": message, "error_code": "oauth_provider_error"},
        )

    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "detail": "OAuth callback is missing code",
                "error_code": "oauth_code_missing",
            },
        )

    token, redirect_to_frontend = oauth_external.authenticate_oauth_callback(
        db,
        request,
        provider=provider,
        code=code,
        state_token=state,
    )
    if redirect_to_frontend:
        redirect_url = oauth_external.build_frontend_success_redirect(provider, token)
        return RedirectResponse(redirect_url, status_code=status.HTTP_302_FOUND)
    return token


@router.get("/auth/oauth/{provider}/start")
def oauth_start(
    provider: str,
    request: Request,
    redirect_to_frontend: bool = True,
    _: None = rate_limit_dependency("auth_login"),
):
    authorize_url = oauth_external.build_authorization_url(
        provider,
        request,
        redirect_to_frontend=redirect_to_frontend,
    )
    return RedirectResponse(authorize_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@router.get("/auth/oauth/{provider}/callback", response_model=schemas.Token)
async def oauth_callback_get(
    provider: str,
    request: Request,
    state: Optional[str] = None,
    code: Optional[str] = None,
    error: Optional[str] = None,
    error_description: Optional[str] = None,
    _: None = rate_limit_dependency("auth_login"),
    db: Session = Depends(database.get_db),
):
    return await _handle_oauth_callback(
        provider,
        request,
        state=state,
        code=code,
        error=error,
        error_description=error_description,
        db=db,
    )


@router.post("/auth/oauth/{provider}/callback", response_model=schemas.Token)
async def oauth_callback_post(
    provider: str,
    request: Request,
    state: Optional[str] = Form(default=None),
    code: Optional[str] = Form(default=None),
    error: Optional[str] = Form(default=None),
    error_description: Optional[str] = Form(default=None),
    _: None = rate_limit_dependency("auth_login"),
    db: Session = Depends(database.get_db),
):
    return await _handle_oauth_callback(
        provider,
        request,
        state=state,
        code=code,
        error=error,
        error_description=error_description,
        db=db,
    )
