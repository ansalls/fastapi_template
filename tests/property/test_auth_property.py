import pytest
from app import oauth2
from fastapi import HTTPException, status
from hypothesis import given
from hypothesis import strategies as st

pytestmark = [pytest.mark.unit, pytest.mark.property]


def _credentials_exception():
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


@given(st.integers(min_value=1, max_value=10_000_000))
def test_access_token_roundtrip_preserves_user_id(user_id: int):
    token = oauth2.create_access_token({"user_id": user_id})
    token_data = oauth2.verify_access_token(token, _credentials_exception())

    assert token_data.id == user_id


@given(st.text(min_size=1, max_size=60))
def test_random_non_jwt_tokens_are_rejected(random_text: str):
    # Ensure we only test truly malformed values, not accidental JWTs.
    assume_jwt_like = random_text.count(".") >= 2
    if assume_jwt_like:
        random_text = f"{random_text}-not-a-jwt"

    with pytest.raises(HTTPException) as exc_info:
        oauth2.verify_access_token(random_text, _credentials_exception())

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
