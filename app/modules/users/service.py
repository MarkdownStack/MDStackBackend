"""Business logic for accounts, auth, and email. Behavior unchanged from
before this migration; `current_user["_id"]`/user ids are `uuid.UUID`
instead of bson `ObjectId`, and every DB call now takes the request's
`AsyncSession`."""

import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from ...core.exceptions import (
    AuthenticationError,
    BadRequestError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
)
from ...core.security import create_access_token, hash_password, verify_password
from ...db.models import User, UserPreferences
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


def _new_token(ttl: timedelta) -> tuple[str, datetime]:
    """Returns (token, expiry) for a fresh single-use link."""
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + ttl
    return token, expires_at


def _new_verification_token() -> tuple[str, datetime]:
    return _new_token(VERIFICATION_TOKEN_TTL)


async def register(db: AsyncSession, payload: UserCreate) -> UserOut:
    email = payload.email.lower()
    # Lowercased for the same reason email is — keeps "Parimal" and
    # "parimal" from registering as two different (but visually identical)
    # login identifiers, and matches how login/find_by_identifier looks it
    # up.
    username = payload.username.lower()

    if await repository.find_by_email(db, email):
        raise ConflictError("Email already registered")
    if await repository.find_by_username(db, username):
        raise ConflictError("Username already taken")

    token, expires_at = _new_verification_token()
    user = User(
        username=username,
        email=email,
        password_hash=hash_password(payload.password),
        is_verified=False,
        verification_token=token,
        verification_token_expires=expires_at,
    )
    await repository.insert_user(db, user)
    # Every account gets a preferences row up front (dark mode, autosave
    # interval, etc. — see db/models.py's UserPreferences) rather than
    # lazily on first GET /api/preferences, so the one-to-one relationship
    # this migration's brief calls for always actually holds: every user
    # row has exactly one preferences row, never zero.
    db.add(UserPreferences(user_id=user.id))

    # Best-effort: registration still succeeds even if Mailgun is down or
    # unconfigured (see send_verification_email's docstring) — the account
    # exists either way, "resend verification" is the recovery path.
    await send_verification_email(email, token)

    return to_user_out(user)


async def login(db: AsyncSession, identifier: str, password: str) -> Token:
    # OAuth2PasswordRequestForm's field is literally named "username", but
    # the router passes through whatever the caller sent as either a real
    # username or an email address — AuthPage.jsx's login field is labeled
    # "Email or username" accordingly.
    user = await repository.find_by_identifier(db, identifier)
    if not user or not verify_password(password, user.password_hash):
        raise AuthenticationError("Incorrect email/username or password")

    if not user.is_verified:
        # 403, not 401 — the credentials themselves were correct, the
        # account just isn't activated yet. AuthPage.jsx keys off this
        # status specifically to show "resend verification" instead of a
        # generic wrong-password error.
        raise PermissionDeniedError("Please verify your email before logging in.")

    access_token = create_access_token(data={"sub": str(user.id)})
    return Token(access_token=access_token)


async def verify_email(db: AsyncSession, token: str) -> str:
    user = await repository.find_by_verification_token(db, token)
    if not user:
        raise BadRequestError("This verification link is invalid or has already been used.")

    if user.is_verified:
        return "Your email is already verified — you can log in."

    if user.verification_token_expires and datetime.now(timezone.utc) > user.verification_token_expires:
        raise BadRequestError("This verification link has expired. Request a new one from the login page.")

    await repository.mark_verified(db, user)
    return "Email verified! You can now log in."


async def resend_verification(db: AsyncSession, identifier: str) -> str:
    user = await repository.find_by_identifier(db, identifier)

    # Identical response whether the account exists, is already verified,
    # or genuinely gets a new email — so this endpoint can't be used to
    # probe which addresses/usernames have an account.
    generic = "If that account exists and needs verifying, a new link is on its way."

    if not user or user.is_verified:
        return generic

    token, expires_at = _new_verification_token()
    await repository.set_verification_token(db, user, token, expires_at)
    # Always to the account's real email on file — never wherever the
    # caller's `identifier` happened to point, since that might be a
    # username rather than an address at all.
    await send_verification_email(user.email, token)
    return generic


async def forgot_password(db: AsyncSession, identifier: str) -> str:
    user = await repository.find_by_identifier(db, identifier)

    # Same generic response regardless of whether the account exists — see
    # resend_verification above for why (enumeration prevention).
    generic = "If that account exists, a password reset link is on its way."

    if not user:
        return generic

    token, expires_at = _new_token(PASSWORD_RESET_TOKEN_TTL)
    await repository.set_password_reset_token(db, user, token, expires_at)
    await send_password_reset_email(user.email, token)
    return generic


async def reset_password(db: AsyncSession, token: str, password: str) -> str:
    user = await repository.find_by_reset_token(db, token)
    if not user:
        raise BadRequestError("This reset link is invalid or has already been used.")

    if user.password_reset_token_expires and datetime.now(timezone.utc) > user.password_reset_token_expires:
        raise BadRequestError("This reset link has expired. Request a new one from the login page.")

    await repository.update_password(db, user, hash_password(password))
    return "Password reset! You can now log in with your new password."


async def get_profile(db: AsyncSession, user_id: uuid.UUID) -> UserOut:
    # The one endpoint that actually needs more than the user's id —
    # get_current_user no longer fetches the full row itself (see its
    # docstring), so this fetches it explicitly, just for this rarer call.
    user = await repository.find_by_id(db, user_id)
    if not user:
        raise NotFoundError("User not found")
    return to_user_out(user)
