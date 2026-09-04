import jwt
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from .auth import decode_access_token

# tokenUrl points the interactive docs (/docs) at the login endpoint
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    """Decode the bearer token and return a lightweight identity: {"_id": ObjectId}.

    This used to also fetch the full user document from MongoDB on *every*
    request — which, since this dependency runs in front of nearly every
    endpoint in the app, meant an extra full network round trip on top of
    whatever each endpoint's own queries needed. Checking every consumer
    across notes/folders/tags/search/upload confirms none of them ever read
    anything from `current_user` except `_id` — the one exception,
    /api/auth/me, now fetches the full profile itself in the rare case it's
    actually needed. So the common path here just trusts the signed JWT's
    `sub` claim, with no DB call at all.

    Trade-off: a token stays valid for its full lifetime even if the
    account were deleted in the meantime — the standard trade-off of
    stateless JWT auth (vs. a DB-backed session). Tokens here already expire
    (see ACCESS_TOKEN_EXPIRE_MINUTES in auth.py), and this is a personal
    vault rather than a multi-tenant service with strict revocation needs,
    so that's a reasonable trade for removing a database round trip from
    every single request in the app.
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
        return {"_id": ObjectId(user_id)}
    except (jwt.PyJWTError, InvalidId):
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
        return {"_id": ObjectId(user_id)}
    except (jwt.PyJWTError, InvalidId):
        return None
