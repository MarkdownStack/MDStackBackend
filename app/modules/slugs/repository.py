"""All SQLAlchemy queries for slug_redirects.

Deliberately no business-logic here — service.py owns the "is this note
actually published and does it belong to this user?" checks; this file is
pure data access.
"""

import uuid

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.models import SlugRedirect


async def find_by_slug(session: AsyncSession, slug: str) -> SlugRedirect | None:
    result = await session.execute(select(SlugRedirect).where(SlugRedirect.slug == slug))
    return result.scalar_one_or_none()


async def find_by_target(
    session: AsyncSession, target_type: str, target_id: uuid.UUID
) -> SlugRedirect | None:
    result = await session.execute(
        select(SlugRedirect).where(
            SlugRedirect.target_type == target_type,
            SlugRedirect.target_id == target_id,
        )
    )
    return result.scalar_one_or_none()


async def upsert(
    session: AsyncSession,
    owner_id: uuid.UUID,
    slug: str,
    target_type: str,
    target_id: uuid.UUID,
) -> SlugRedirect:
    """Set (or replace) the slug for a given target. Deletes the old row
    for this target first so the unique constraint on (target_type,
    target_id) is never violated, then inserts the new one. The delete is
    also what clears a previously claimed global slug: if another row
    happened to hold the *new* slug value, that row belongs to a different
    target — the unique-slug constraint would catch it before we ever reach
    this point (service.py checks availability first)."""
    from datetime import datetime, timezone

    # Remove any existing slug row for this target (there can be at most one).
    await session.execute(
        delete(SlugRedirect).where(
            SlugRedirect.target_type == target_type,
            SlugRedirect.target_id == target_id,
        )
    )
    await session.flush()

    now = datetime.now(timezone.utc)
    row = SlugRedirect(
        owner_id=owner_id,
        slug=slug,
        target_type=target_type,
        target_id=target_id,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    await session.flush()
    return row


async def delete_by_target(
    session: AsyncSession, target_type: str, target_id: uuid.UUID
) -> None:
    """Remove a slug entry entirely — used when a note/folder is
    unpublished, so its slug doesn't sit around pointing at content that
    is no longer public."""
    await session.execute(
        delete(SlugRedirect).where(
            SlugRedirect.target_type == target_type,
            SlugRedirect.target_id == target_id,
        )
    )
