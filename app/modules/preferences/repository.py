"""All SQLAlchemy queries for the user_preferences table."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.models import UserPreferences


async def get_by_user_id(session: AsyncSession, user_id: uuid.UUID) -> UserPreferences | None:
    result = await session.execute(select(UserPreferences).where(UserPreferences.user_id == user_id))
    return result.scalar_one_or_none()


async def get_or_create(session: AsyncSession, user_id: uuid.UUID) -> UserPreferences:
    """Every account gets a preferences row at registration time (see
    modules/users/service.py's register()) — this fallback only matters
    for accounts that existed before this migration and haven't been
    backfilled yet, so GET /api/preferences never 404s for a real user."""
    prefs = await get_by_user_id(session, user_id)
    if prefs is None:
        prefs = UserPreferences(user_id=user_id)
        session.add(prefs)
        await session.flush()
    return prefs
