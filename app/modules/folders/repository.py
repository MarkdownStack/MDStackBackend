"""All SQLAlchemy queries for the folders table (and the notes queries
folder operations need — cascade delete and published-folder note counts
both scope across both tables at once)."""

import uuid
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.models import Folder, Note
from ...shared.paths import folder_scope_clause


async def list_explicit_paths(session: AsyncSession, owner_id: uuid.UUID) -> set[str]:
    result = await session.execute(select(Folder.path).where(Folder.owner_id == owner_id))
    return set(result.scalars().all())


async def list_implied_paths(session: AsyncSession, owner_id: uuid.UUID) -> set[str]:
    result = await session.execute(
        select(Note.folder_path).where(Note.owner_id == owner_id, Note.folder_path != "").distinct()
    )
    return set(result.scalars().all())


async def find_by_path(session: AsyncSession, owner_id: uuid.UUID, path: str) -> Folder | None:
    result = await session.execute(select(Folder).where(Folder.owner_id == owner_id, Folder.path == path))
    return result.scalar_one_or_none()


async def insert(session: AsyncSession, owner_id: uuid.UUID, path: str, ts: datetime) -> Folder:
    folder = Folder(owner_id=owner_id, path=path, created_at=ts, updated_at=ts)
    session.add(folder)
    await session.flush()
    return folder


async def find_one_folder_matching_scope(session: AsyncSession, owner_id: uuid.UUID, path: str) -> Folder | None:
    result = await session.execute(
        select(Folder).where(Folder.owner_id == owner_id, folder_scope_clause(Folder.path, path)).limit(1)
    )
    return result.scalar_one_or_none()


async def find_one_note_matching_scope(session: AsyncSession, owner_id: uuid.UUID, path: str) -> Note | None:
    result = await session.execute(
        select(Note).where(Note.owner_id == owner_id, folder_scope_clause(Note.folder_path, path)).limit(1)
    )
    return result.scalar_one_or_none()


async def delete_scope(session: AsyncSession, owner_id: uuid.UUID, path: str) -> tuple[int, int]:
    """Deletes every note and folder row in this owner's subtree scoped to
    `path`. Returns (deleted_notes_count, deleted_folders_count)."""
    notes_result = await session.execute(
        delete(Note).where(Note.owner_id == owner_id, folder_scope_clause(Note.folder_path, path))
    )
    folders_result = await session.execute(
        delete(Folder).where(Folder.owner_id == owner_id, folder_scope_clause(Folder.path, path))
    )
    return notes_result.rowcount, folders_result.rowcount


async def list_published(session: AsyncSession, owner_id: uuid.UUID) -> list[Folder]:
    result = await session.execute(
        select(Folder)
        .where(Folder.owner_id == owner_id, Folder.is_public.is_(True))
        .order_by(Folder.updated_at.desc())
    )
    return list(result.scalars().all())


async def count_notes_matching_scope(session: AsyncSession, owner_id: uuid.UUID, path: str) -> int:
    result = await session.execute(
        select(func.count())
        .select_from(Note)
        .where(Note.owner_id == owner_id, folder_scope_clause(Note.folder_path, path))
    )
    return result.scalar_one()


async def upsert_publish(session: AsyncSession, owner_id: uuid.UUID, path: str, is_public: bool, ts: datetime) -> Folder:
    folder = await find_by_path(session, owner_id, path)
    if folder is None:
        folder = Folder(owner_id=owner_id, path=path, is_public=is_public, created_at=ts, updated_at=ts)
        session.add(folder)
    else:
        folder.is_public = is_public
        folder.updated_at = ts
    await session.flush()
    return folder
