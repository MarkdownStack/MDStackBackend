"""Auth dependencies.

Behavior unchanged from the Mongo version's shared/dependencies.py; what
moved is the identity type (`current_user["_id"]` is now a `uuid.UUID`
instead of a bson `ObjectId`) and get_current_admin's lookup (a SQLAlchemy
query via an injected `AsyncSession` instead of a Motor collection global).
"""

import uuid

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import get_settings
from ..core.security import decode_access_token
from ..db.models import User
from ..db.postgres import get_db

settings = get_settings()


def is_admin_email(email: str | None) -> bool:
    """Shared by get_current_admin below and modules/users/models.py's
    to_user_out (which surfaces this as UserOut.is_admin so the frontend
    can show/hide admin-only UI without guessing)."""
    return bool(email) and email.strip().lower() in settings.admin_email_set


# tokenUrl points the interactive docs (/docs) at the login endpoint
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    """Decode the bearer token and return a lightweight identity:
    {"_id": uuid.UUID}.

    Same trade-off as before this migration: the common path trusts the
    signed JWT's `sub` claim with no database round trip at all (every
    consumer across notes/folders/tags/search/upload only ever reads
    `current_user["_id"]`) — a token stays valid for its full lifetime
    even if the account were deleted in the meantime, the standard
    trade-off of stateless JWT auth for a personal-vault-scale app. See
    modules/users/service.py's get_profile for the one place that fetches
    the full row.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = decode_access_token(token)
        user_id = payload.get("sub")
        if user_id is None:
            raise credentials_exception
        return {"_id": uuid.UUID(user_id)}
    except (jwt.PyJWTError, ValueError, AttributeError, TypeError):
        raise credentials_exception


# tokenUrl the same as above, but auto_error=False means "no/invalid token"
# resolves to None here instead of raising — for the handful of endpoints
# that behave the same for anyone but want to *personalize* the response
# when the caller happens to be logged in (see list_public_notes, which
# excludes the caller's own notes from the "other people's notes" feed).
optional_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


async def get_current_user_optional(token: str | None = Depends(optional_oauth2_scheme)) -> dict | None:
    if not token:
        return None
    try:
        payload = decode_access_token(token)
        user_id = payload.get("sub")
        if user_id is None:
            return None
        return {"_id": uuid.UUID(user_id)}
    except (jwt.PyJWTError, ValueError, AttributeError, TypeError):
        return None


async def get_current_admin(
    current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> dict:
    """Same identity as get_current_user, but 403s unless that user's
    email is in Settings.admin_email_set. Does the one extra DB round
    trip get_current_user's own docstring explains it normally avoids —
    acceptable here since admin-only endpoints are low-traffic by
    nature."""
    result = await db.execute(select(User.email).where(User.id == current_user["_id"]))
    email = result.scalar_one_or_none()
    if not email or not is_admin_email(email):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user
