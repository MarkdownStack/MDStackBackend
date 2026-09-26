"""All SQLAlchemy queries for the comments table."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.models import Comment


async def list_by_note(session: AsyncSession, note_id: uuid.UUID) -> list[Comment]:
    result = await session.execute(select(Comment).where(Comment.note_id == note_id).order_by(Comment.created_at.asc()))
    return list(result.scalars().all())


async def insert(session: AsyncSession, comment: Comment) -> Comment:
    session.add(comment)
    await session.flush()
    return comment


async def upvote(session: AsyncSession, comment_id: uuid.UUID, note_id: uuid.UUID) -> Comment | None:
    result = await session.execute(
        select(Comment).where(Comment.id == comment_id, Comment.note_id == note_id)
    )
    comment = result.scalar_one_or_none()
    if comment is None:
        return None
    comment.upvotes += 1
    await session.flush()
    return comment


async def update_content(session: AsyncSession, comment_id: uuid.UUID, owner_id: uuid.UUID, content: str) -> Comment | None:
    """Update a comment's content — scoped to owner_id so a user can never
    edit someone else's comment even if they somehow know the comment_id."""
    from datetime import datetime, timezone
    result = await session.execute(
        select(Comment).where(Comment.id == comment_id, Comment.owner_id == owner_id)
    )
    comment = result.scalar_one_or_none()
    if comment is None:
        return None
    comment.content = content
    comment.updated_at = datetime.now(timezone.utc)
    await session.flush()
    return comment


async def delete(session: AsyncSession, comment_id: uuid.UUID, owner_id: uuid.UUID) -> bool:
    """Delete a comment — scoped to owner_id so a user can never delete
    someone else's comment. Returns True if something was deleted."""
    result = await session.execute(
        select(Comment).where(Comment.id == comment_id, Comment.owner_id == owner_id)
    )
    comment = result.scalar_one_or_none()
    if comment is None:
        return False
    await session.delete(comment)
    await session.flush()
    return True


async def counts_for_notes(session: AsyncSession, note_ids: list[str]) -> dict[str, int]:
    """Batch note_id (str) -> comment count in one query, instead of one
    round trip per note in a list — used by the anonymous Explore feed
    (modules/public) and "my published notes" (modules/notes) so both
    render comment counts identically. Takes/returns plain id strings
    (matching how every call site already has them, from `str(note.id)`)
    rather than pushing uuid.UUID conversion onto every caller."""
    uuids: list[uuid.UUID] = []
    for note_id in note_ids:
        try:
            uuids.append(uuid.UUID(note_id))
        except (ValueError, AttributeError, TypeError):
            continue
    if not uuids:
        return {}
    result = await session.execute(
        select(Comment.note_id, func.count(Comment.id)).where(Comment.note_id.in_(uuids)).group_by(Comment.note_id)
    )
    return {str(note_id): count for note_id, count in result.all()}
