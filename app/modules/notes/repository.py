"""All SQLAlchemy queries for the notes table (and its many-to-many with
tags) — replaces the Motor calls that used to live here."""

import uuid

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ...db.models import Note, Tag, note_tags


async def find_by_title(session: AsyncSession, owner_id: uuid.UUID, title: str) -> Note | None:
    result = await session.execute(select(Note).where(Note.owner_id == owner_id, Note.title == title))
    return result.scalar_one_or_none()


async def find_by_title_excluding(
    session: AsyncSession, owner_id: uuid.UUID, title: str, exclude_id: uuid.UUID
) -> Note | None:
    result = await session.execute(
        select(Note).where(Note.owner_id == owner_id, Note.title == title, Note.id != exclude_id)
    )
    return result.scalar_one_or_none()


async def find_by_id(session: AsyncSession, owner_id: uuid.UUID, note_id: uuid.UUID) -> Note | None:
    result = await session.execute(
        select(Note).options(selectinload(Note.tags)).where(Note.id == note_id, Note.owner_id == owner_id)
    )
    return result.scalar_one_or_none()


async def find_titles_linking_to(
    session: AsyncSession, owner_id: uuid.UUID, title: str, exclude_id: uuid.UUID | None = None
) -> list[dict]:
    """Find all of this user's notes whose `links` array contains this
    note's title — array containment (`title = ANY(notes.links)`), not a
    regex or substring match."""
    query = select(Note.id, Note.title).where(Note.owner_id == owner_id, Note.links.any(title))
    if exclude_id is not None:
        query = query.where(Note.id != exclude_id)
    result = await session.execute(query)
    return [{"id": str(row.id), "title": row.title} for row in result.all()]


async def list_by_owner(session: AsyncSession, owner_id: uuid.UUID, folder_path: str | None) -> list[Note]:
    query = select(Note).options(selectinload(Note.tags)).where(Note.owner_id == owner_id)
    if folder_path is not None:
        query = query.where(Note.folder_path == folder_path)
    query = query.order_by(Note.updated_at.desc())
    result = await session.execute(query)
    return list(result.scalars().all())


async def list_published_by_owner(session: AsyncSession, owner_id: uuid.UUID) -> list[Note]:
    # Same card shape/sort as the anonymous Explore feed in modules/public.
    query = (
        select(Note)
        .options(selectinload(Note.tags))
        .where(Note.owner_id == owner_id, Note.is_public.is_(True))
        .order_by(Note.upvotes.desc(), Note.updated_at.desc())
    )
    result = await session.execute(query)
    return list(result.scalars().all())


async def insert(session: AsyncSession, note: Note) -> Note:
    session.add(note)
    await session.flush()  # populates note.id/created_at/updated_at before commit
    return note


async def delete(session: AsyncSession, owner_id: uuid.UUID, note_id: uuid.UUID) -> int:
    note = await find_by_id(session, owner_id, note_id)
    if note is None:
        return 0
    await session.delete(note)
    await session.flush()
    return 1


async def get_or_create_tags(session: AsyncSession, owner_id: uuid.UUID, names: list[str]) -> list[Tag]:
    """Get-or-create Tag rows for `names` (case-sensitive, exactly as
    extract_tags produced them), scoped to this owner. Used to populate
    Note.tags on create/update — see modules/notes/service.py."""
    if not names:
        return []
    result = await session.execute(select(Tag).where(Tag.owner_id == owner_id, Tag.name.in_(names)))
    existing = {tag.name: tag for tag in result.scalars().all()}
    tags: list[Tag] = []
    for name in names:
        tag = existing.get(name)
        if tag is None:
            tag = Tag(owner_id=owner_id, name=name)
            session.add(tag)
            existing[name] = tag
        tags.append(tag)
    return tags


# ---------------------------------------------------------------------------
# Queries for modules/search and modules/tags — both are thin modules with
# no table of their own, so they call straight into this repository rather
# than duplicating notes/tags access.
# ---------------------------------------------------------------------------


async def text_search(session: AsyncSession, owner_id: uuid.UUID, q: str, limit: int = 30) -> list[Note]:
    """Full-text search across title + content, using the stored
    `search_vector` generated column (see db/models.py) — the direct
    Postgres equivalent of the old Mongo `$text` index.
    `plainto_tsquery` is Postgres's own text-search query parser, not a
    regular expression."""
    ts_query = func.plainto_tsquery("english", q)
    rank = func.ts_rank(Note.search_vector, ts_query).label("rank")
    query = (
        select(Note)
        .options(selectinload(Note.tags))
        .where(Note.owner_id == owner_id, Note.search_vector.op("@@")(ts_query))
        .order_by(rank.desc())
        .limit(limit)
    )
    result = await session.execute(query)
    return list(result.scalars().all())


async def tag_counts(session: AsyncSession, owner_id: uuid.UUID) -> list[dict]:
    query = (
        select(Tag.name, func.count(note_tags.c.note_id).label("count"))
        .join(note_tags, note_tags.c.tag_id == Tag.id)
        .where(Tag.owner_id == owner_id)
        .group_by(Tag.name)
        .order_by(text("count DESC"), Tag.name.asc())
    )
    result = await session.execute(query)
    return [{"tag": name, "count": count} for name, count in result.all()]


async def list_by_tag(session: AsyncSession, owner_id: uuid.UUID, tag: str) -> list[Note]:
    query = (
        select(Note)
        .options(selectinload(Note.tags))
        .join(note_tags, note_tags.c.note_id == Note.id)
        .join(Tag, Tag.id == note_tags.c.tag_id)
        .where(Note.owner_id == owner_id, Tag.name == tag)
    )
    result = await session.execute(query)
    return list(result.scalars().all())
