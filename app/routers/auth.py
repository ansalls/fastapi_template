from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.security.oauth2 import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from .. import database, models, oauth2, schemas, utils
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
