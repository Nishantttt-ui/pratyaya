"""Token issuance."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from backend.app.api.deps import SettingsDep, UsersDep
from backend.app.core.security import TokenSubject, create_access_token
from backend.app.schemas.assessment import TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/token", response_model=TokenResponse)
async def issue_token(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    users: UsersDep,
    settings: SettingsDep,
) -> TokenResponse:
    """Exchange credentials for a short-lived bearer token."""
    user = users.authenticate(form.username, form.password)
    if user is None:
        # One message for both unknown-user and wrong-password, so the endpoint
        # cannot be used to enumerate valid usernames.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(
        TokenSubject(username=user.username, role=user.role), settings
    )
    return TokenResponse(
        access_token=token,
        role=str(user.role),
        expires_in_minutes=settings.access_token_expire_minutes,
    )
