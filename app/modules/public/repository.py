"""All SQLAlchemy queries the /api/public note/folder routes need.

count_comments_for_note below is the one exception to "comments belong to
modules/comments": it's the exact single-note count the original code ran
directly against the comments table (not through any comments
abstraction), kept here rather than imported from modules/comments so this
module and modules/comments don't end up needing each other's service
layer — see modules/comments/service.py's own note on the one-way
dependency this keeps (comments -> public, never the reverse).
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ...db.models import Comment, Folder, Note
from ...shared.paths import folder_scope_clause


async def find_public_note(session: AsyncSession, note_id: uuid.UUID) -> Note | None:
    result = await session.execute(
        select(Note).options(selectinload(Note.tags)).where(Note.id == note_id, Note.is_public.is_(True))
    )
    return result.scalar_one_or_none()


async def find_public_folder(session: AsyncSession, folder_id: uuid.UUID) -> Folder | None:
    result = await session.execute(select(Folder).where(Folder.id == folder_id, Folder.is_public.is_(True)))
    return result.scalar_one_or_none()


async def count_comments_for_note(session: AsyncSession, note_id: uuid.UUID) -> int:
    result = await session.execute(select(func.count()).select_from(Comment).where(Comment.note_id == note_id))
    return result.scalar_one()


async def list_public_notes(session: AsyncSession, exclude_owner_id: uuid.UUID | None, limit: int) -> list[Note]:
    query = select(Note).options(selectinload(Note.tags)).where(Note.is_public.is_(True))
    if exclude_owner_id is not None:
        query = query.where(Note.owner_id != exclude_owner_id)
    query = query.order_by(Note.upvotes.desc(), Note.updated_at.desc()).limit(limit)
    result = await session.execute(query)
    return list(result.scalars().all())


async def vote_note(session: AsyncSession, note_id: uuid.UUID, up_delta: int, down_delta: int) -> Note:
    """Clamped in plain Python (`max(0, ...)`), not a SQL `GREATEST()`
    expression — assigning a SQL expression to an ORM attribute leaves it
    "expired" until a follow-up `session.refresh()`, which is easy to get
    wrong under asyncio (see db/models.py's User.updated_at comment on the
    same trap). A plain int assignment needs no refresh at all. Note this
    deliberately never touches `updated_at` — same as the old Mongo
    version, voting doesn't count as "updating" a note for feed-sorting
    purposes."""
    note = await session.get(Note, note_id, options=[selectinload(Note.tags)])
    note.upvotes = max(0, note.upvotes + up_delta)
    note.downvotes = max(0, note.downvotes + down_delta)
    await session.flush()
    return note


async def list_public_folders(session: AsyncSession, exclude_owner_id: uuid.UUID | None, limit: int) -> list[Folder]:
    query = select(Folder).where(Folder.is_public.is_(True))
    if exclude_owner_id is not None:
        query = query.where(Folder.owner_id != exclude_owner_id)
    query = query.order_by(Folder.updated_at.desc()).limit(limit)
    result = await session.execute(query)
    return list(result.scalars().all())


async def list_notes_in_folder(session: AsyncSession, owner_id: uuid.UUID, path: str) -> list[Note]:
    query = (
        select(Note)
        .options(selectinload(Note.tags))
        .where(Note.owner_id == owner_id, folder_scope_clause(Note.folder_path, path))
        .order_by(Note.folder_path.asc(), Note.title.asc())
    )
    result = await session.execute(query)
    return list(result.scalars().all())


async def find_note_by_owner(session: AsyncSession, owner_id: uuid.UUID, note_id: uuid.UUID) -> Note | None:
    result = await session.execute(select(Note).where(Note.id == note_id, Note.owner_id == owner_id))
    return result.scalar_one_or_none()
