"""Authentication, password hashing and role-based authorisation.

Roles
-----
``applicant`` sees their own decision: the outcome, the reasons in plain
language, what would change it, and the provisions that apply.

``underwriter`` additionally sees the machinery: the calibrated probability,
the signed contribution of every reason code, the decision threshold, and the
provenance block showing whether the wording was generated or deterministic.

The split is not cosmetic. Showing an applicant a raw probability of default
invites them to argue with a number they cannot audit, while withholding the
reasons from them would breach the Fair Practices Code. Different audiences
need different views of the same decision.

Passwords are hashed with bcrypt and never stored or logged in clear text. The
signing secret is read from the environment and validated at startup; there is
no in-code default.
"""

from __future__ import annotations

import base64
import hashlib
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Annotated

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel

from backend.app.core.config import Settings, get_settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token", auto_error=False)


def _prehash(password: str) -> bytes:
    """Reduce a password to a fixed 44-byte token before bcrypt sees it.

    bcrypt silently ignores anything past the 72nd byte, which would make two
    long passwords sharing a 72-byte prefix interchangeable. Hashing with
    SHA-256 and base64-encoding first makes every input exactly 44 bytes, so
    the whole password contributes and the limit cannot be reached.

    We use bcrypt directly rather than passlib: passlib is unmaintained and its
    backend-detection probe hashes a password longer than 72 bytes, which
    raises outright on bcrypt 4.1 and later.
    """
    digest = hashlib.sha256(password.encode("utf-8")).digest()
    return base64.b64encode(digest)


class Role(StrEnum):
    APPLICANT = "applicant"
    UNDERWRITER = "underwriter"


class TokenSubject(BaseModel):
    username: str
    role: Role


def hash_password(password: str) -> str:
    """Hash a password for storage. Never log or return the input."""
    return bcrypt.hashpw(_prehash(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Constant-time comparison of a candidate password against a stored hash."""
    try:
        return bcrypt.checkpw(_prehash(plain), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(subject: TokenSubject, settings: Settings | None = None) -> str:
    """Mint a short-lived bearer token."""
    settings = settings or get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": subject.username,
        "role": str(subject.role),
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(
        payload, settings.jwt_secret.get_secret_value(), algorithm=settings.jwt_algorithm
    )


def decode_access_token(token: str, settings: Settings | None = None) -> TokenSubject:
    """Validate a bearer token, raising 401 on any problem."""
    settings = settings or get_settings()
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.PyJWTError as exc:
        raise credentials_error from exc

    username = payload.get("sub")
    role = payload.get("role")
    if not username or role not in set(Role):
        raise credentials_error
    return TokenSubject(username=username, role=Role(role))


async def get_current_user(
    token: Annotated[str | None, Depends(oauth2_scheme)],
) -> TokenSubject:
    """FastAPI dependency resolving the caller from their bearer token."""
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return decode_access_token(token)


def require_role(*allowed: Role):
    """Dependency factory restricting an endpoint to the given roles."""

    async def _guard(
        user: Annotated[TokenSubject, Depends(get_current_user)],
    ) -> TokenSubject:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of: {', '.join(str(r) for r in allowed)}",
            )
        return user

    return _guard
