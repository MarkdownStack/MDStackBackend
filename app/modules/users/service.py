"""Business logic for accounts, auth, and email — moved from
app/routers/auth.py. Behavior unchanged; HTTPException is replaced with
the equivalent domain exception from core/exceptions.py (same status
code, same detail string, same headers)."""

import secrets
from datetime import datetime, timedelta, timezone

from bson import ObjectId

from ...core.exceptions import (
    AuthenticationError,
    BadRequestError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
)
from ...core.security import create_access_token, hash_password, verify_password
from ...shared.datetime import now_iso
from . import repository
from .email import send_password_reset_email, send_verification_email
from .models import to_user_out
from .schemas import Token, UserCreate, UserOut

# How long a verification link stays clickable before verify_email starts
# rejecting it (and the user has to hit "resend" to get a fresh one).
VERIFICATION_TOKEN_TTL = timedelta(hours=24)

# Deliberately much shorter than the verification token above — a password
# reset link grants "set this account's password" outright (no old
# password needed), so a short window matters more here than for email
# verification.
PASSWORD_RESET_TOKEN_TTL = timedelta(hours=1)


def _new_token(ttl: timedelta) -> tuple[str, str]:
    """Returns (token, ISO-8601 expiry) for a fresh single-use link."""
    token = secrets.token_urlsafe(32)
    expires_at = (datetime.now(timezone.utc) + ttl).isoformat()
    return token, expires_at


def _new_verification_token() -> tuple[str, str]:
    return _new_token(VERIFICATION_TOKEN_TTL)


async def register(payload: UserCreate) -> UserOut:
    email = payload.email.lower()
    # Lowercased for the same reason email is — keeps "Parimal" and
    # "parimal" from registering as two different (but visually identical)
    # login identifiers, and matches how login/find_by_identifier looks it
    # up.
    username = payload.username.lower()

    if await repository.find_by_email(email):
        raise ConflictError("Email already registered")
    if await repository.find_by_username(username):
        raise ConflictError("Username already taken")

    ts = now_iso()
    token, expires_at = _new_verification_token()
    doc = {
        "username": username,
        "email": email,
        "password_hash": hash_password(payload.password),
        "is_verified": False,
        "verification_token": token,
        "verification_token_expires": expires_at,
        "created_at": ts,
        "updated_at": ts,
    }
    user_id = await repository.insert_user(doc)
    doc["_id"] = user_id

    # Best-effort: registration still succeeds even if Mailgun is down or
    # unconfigured (see send_verification_email's docstring) — the account
    # exists either way, "resend verification" is the recovery path.
    await send_verification_email(email, token)

    return to_user_out(doc)


async def login(identifier: str, password: str) -> Token:
    # OAuth2PasswordRequestForm's field is literally named "username", but
    # the router passes through whatever the caller sent as either a real
    # username or an email address — AuthPage.jsx's login field is labeled
    # "Email or username" accordingly.
    user = await repository.find_by_identifier(identifier)
    if not user or not verify_password(password, user["password_hash"]):
        raise AuthenticationError("Incorrect email/username or password")

    if not user.get("is_verified", False):
        # 403, not 401 — the credentials themselves were correct, the
        # account just isn't activated yet. AuthPage.jsx keys off this
        # status specifically to show "resend verification" instead of a
        # generic wrong-password error.
        raise PermissionDeniedError("Please verify your email before logging in.")

    access_token = create_access_token(data={"sub": str(user["_id"])})
    return Token(access_token=access_token)


async def verify_email(token: str) -> str:
    user = await repository.find_by_verification_token(token)
    if not user:
        raise BadRequestError("This verification link is invalid or has already been used.")

    if user.get("is_verified"):
        return "Your email is already verified — you can log in."

    expires_raw = user.get("verification_token_expires")
    if expires_raw and datetime.now(timezone.utc) > datetime.fromisoformat(expires_raw):
        raise BadRequestError("This verification link has expired. Request a new one from the login page.")

    await repository.mark_verified(user["_id"])
    return "Email verified! You can now log in."


async def resend_verification(identifier: str) -> str:
    user = await repository.find_by_identifier(identifier)

    # Identical response whether the account exists, is already verified,
    # or genuinely gets a new email — so this endpoint can't be used to
    # probe which addresses/usernames have an account.
    generic = "If that account exists and needs verifying, a new link is on its way."

    if not user or user.get("is_verified"):
        return generic

    token, expires_at = _new_verification_token()
    await repository.set_verification_token(user["_id"], token, expires_at)
    # Always to the account's real email on file — never wherever the
    # caller's `identifier` happened to point, since that might be a
    # username rather than an address at all.
    await send_verification_email(user["email"], token)
    return generic


async def forgot_password(identifier: str) -> str:
    user = await repository.find_by_identifier(identifier)

    # Same generic response regardless of whether the account exists — see
    # resend_verification above for why (enumeration prevention).
    generic = "If that account exists, a password reset link is on its way."

    if not user:
        return generic

    token, expires_at = _new_token(PASSWORD_RESET_TOKEN_TTL)
    await repository.set_password_reset_token(user["_id"], token, expires_at)
    await send_password_reset_email(user["email"], token)
    return generic


async def reset_password(token: str, password: str) -> str:
    user = await repository.find_by_reset_token(token)
    if not user:
        raise BadRequestError("This reset link is invalid or has already been used.")

    expires_raw = user.get("password_reset_token_expires")
    if expires_raw and datetime.now(timezone.utc) > datetime.fromisoformat(expires_raw):
        raise BadRequestError("This reset link has expired. Request a new one from the login page.")

    await repository.update_password(user["_id"], hash_password(password))
    return "Password reset! You can now log in with your new password."


async def get_profile(user_id: ObjectId) -> UserOut:
    # The one endpoint that actually needs more than the user's id —
    # get_current_user no longer fetches the full document itself (see its
    # docstring), so this fetches it explicitly, just for this rarer call.
    user = await repository.find_by_id(user_id)
    if not user:
        raise NotFoundError("User not found")
    return to_user_out(user)
