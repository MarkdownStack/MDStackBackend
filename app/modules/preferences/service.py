"""Business logic for /api/preferences — new module (see this package's
schemas.py docstring for why)."""

import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from ...core.exceptions import BadRequestError
from ...db.models import UserPreferences
from ...shared.datetime import iso
from . import repository
from .schemas import PreferencesOut, PreferencesUpdate


def _to_out(prefs: UserPreferences) -> PreferencesOut:
    return PreferencesOut(
        theme=prefs.theme,
        autosave_interval_ms=prefs.autosave_interval_ms,
        spotlight_enabled=prefs.spotlight_enabled,
        live_preview_editing_enabled=prefs.live_preview_editing_enabled,
        justify_text_enabled=prefs.justify_text_enabled,
        reading_font_id=prefs.reading_font_id,
        reading_font_size_id=prefs.reading_font_size_id,
        extra=prefs.extra or {},
        created_at=iso(prefs.created_at),
        updated_at=iso(prefs.updated_at),
    )


async def get_preferences(db: AsyncSession, user_id: uuid.UUID) -> PreferencesOut:
    prefs = await repository.get_or_create(db, user_id)
    return _to_out(prefs)


async def update_preferences(db: AsyncSession, user_id: uuid.UUID, payload: PreferencesUpdate) -> PreferencesOut:
    prefs = await repository.get_or_create(db, user_id)

    updates = payload.model_dump(exclude_unset=True)
    if "theme" in updates and updates["theme"] not in ("light", "dark"):
        raise BadRequestError("theme must be 'light' or 'dark'")

    for field, value in updates.items():
        setattr(prefs, field, value)

    if updates:
        # Explicit, app-managed bump — see db/models.py's User.updated_at
        # comment for why this isn't a server-side onupdate trigger.
        prefs.updated_at = datetime.now(timezone.utc)

    await db.flush()
    return _to_out(prefs)
