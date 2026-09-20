"""All SQLAlchemy queries for the users table — replaces the Motor calls
that used to live here."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.models import User


async def find_by_identifier(session: AsyncSession, identifier: str) -> User | None:
    """Look a user up by email OR username — both are stored lowercased
    (see insert_user below), so lowercasing the incoming identifier once
    here matches either column with a single query. Used by login and by
    the resend-verification/forgot-password recovery flows, since someone
    who signed up with a username may not remember (or want to type) their
    email for those either."""
    identifier = identifier.strip().lower()
    if not identifier:
        return None
    result = await session.execute(select(User).where(or_(User.email == identifier, User.username == identifier)))
    return result.scalar_one_or_none()


async def find_by_email(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def find_by_username(session: AsyncSession, username: str) -> User | None:
    result = await session.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()


async def find_by_id(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    return await session.get(User, user_id)


async def find_by_verification_token(session: AsyncSession, token: str) -> User | None:
    result = await session.execute(select(User).where(User.verification_token == token))
    return result.scalar_one_or_none()


async def find_by_reset_token(session: AsyncSession, token: str) -> User | None:
    result = await session.execute(select(User).where(User.password_reset_token == token))
    return result.scalar_one_or_none()


async def insert_user(session: AsyncSession, user: User) -> User:
    session.add(user)
    await session.flush()  # populates user.id/created_at/updated_at before commit
    return user


async def mark_verified(session: AsyncSession, user: User) -> None:
    user.is_verified = True
    user.verification_token = None
    user.verification_token_expires = None
    user.updated_at = datetime.now(timezone.utc)


async def set_verification_token(session: AsyncSession, user: User, token: str, expires_at) -> None:
    user.verification_token = token
    user.verification_token_expires = expires_at
    user.updated_at = datetime.now(timezone.utc)


async def set_password_reset_token(session: AsyncSession, user: User, token: str, expires_at) -> None:
    user.password_reset_token = token
    user.password_reset_token_expires = expires_at
    user.updated_at = datetime.now(timezone.utc)


async def update_password(session: AsyncSession, user: User, password_hash: str) -> None:
    user.password_hash = password_hash
    # Both single-use — a spent (or now-superseded) reset token must never
    # work again, same as verification_token on success.
    user.password_reset_token = None
    user.password_reset_token_expires = None
    user.updated_at = datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Author-name resolution — used by every route that renders a published-
# note listing (the public/anonymous explore feed, "my published notes",
# published folders) so they all resolve author names identically rather
# than each reimplementing (and risking drifting from) their own version.
# ---------------------------------------------------------------------------


def derive_author_name(email: str) -> str:
    """Fallback byline for accounts that predate the `username` field —
    derived from the part of the email before '@',
    'priya.sharma@x.com' -> 'Priya Sharma'. Once every account has a
    username (see schemas.UserCreate), this only ever fires for old rows."""
    local = (email or "").split("@")[0]
    cleaned = local.replace(".", " ").replace("_", " ").replace("-", " ").strip()
    return cleaned.title() if cleaned else "Someone"


async def authors_by_owner_id(session: AsyncSession, owner_ids) -> dict[str, str]:
    """Batch-resolve owner_id (str) -> display author name in a single
    query, instead of one round trip per note in a list. Prefers the
    account's real username; falls back to derive_author_name for
    accounts created before that field existed."""
    uuid_to_owner_id: dict[uuid.UUID, str] = {}
    for owner_id in owner_ids:
        try:
            uuid_to_owner_id[uuid.UUID(owner_id)] = owner_id
        except (ValueError, AttributeError, TypeError):
            continue
    if not uuid_to_owner_id:
        return {}

    result = await session.execute(
        select(User.id, User.email, User.username).where(User.id.in_(uuid_to_owner_id.keys()))
    )
    output: dict[str, str] = {}
    for user_id, email, username in result.all():
        owner_id = uuid_to_owner_id.get(user_id)
        if owner_id:
            output[owner_id] = username or derive_author_name(email)
    return output
