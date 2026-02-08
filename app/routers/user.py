from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import models, oauth2, schemas, utils
from ..database import get_db
from ..outbox import enqueue_outbox_event
from ..rate_limit import rate_limit_dependency

router = APIRouter(prefix="/users", tags=["Users"])


@router.post("/", status_code=status.HTTP_201_CREATED, response_model=schemas.UserOut)
def create_user(
    user: schemas.UserCreate,
    _: None = rate_limit_dependency("auth_register"),
    db: Session = Depends(get_db),
):
    # hash the password - user.password
    hashed_password = utils.hash(user.password)
    user.password = hashed_password
    new_user = models.User(**user.model_dump())
    db.add(new_user)
    try:
        db.flush()
        enqueue_outbox_event(
            db,
            topic="user.created",
            payload={"user_id": new_user.id, "email": new_user.email},
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email is already registered",
        )
    db.refresh(new_user)
    return new_user


@router.get("/{id}", response_model=schemas.UserOut)
def get_user(
    id: int,
    current_user: models.User = Depends(oauth2.get_current_user),
):
    if int(current_user.id) != int(id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this user",
        )
    return current_user
