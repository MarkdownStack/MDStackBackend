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


async def find_by_id(session: AsyncSession, owner_id: uuid.UUID, folder_id: uuid.UUID) -> Folder | None:
    """Fetch a folder by primary key, scoped to the owner — used by
    slugs/service.py to confirm that the caller owns the folder they're
    setting a slug for before we touch the slug_redirects table."""
    result = await session.execute(
        select(Folder).where(Folder.id == folder_id, Folder.owner_id == owner_id)
    )
    return result.scalar_one_or_none()


async def rename_scope(
    session: AsyncSession,
    owner_id: uuid.UUID,
    old_path: str,
    new_path: str,
    ts: datetime,
) -> None:
    """Rewrite every folder row and every note whose path starts with
    old_path (exact match or old_path + "/") to use new_path instead.
    Uses string replacement on the path prefix so deeply-nested children
    like old_path/sub/deep become new_path/sub/deep correctly."""
    from sqlalchemy import update
    from ...db.models import Note

    # Exact folder row match.
    await session.execute(
        update(Folder)
        .where(Folder.owner_id == owner_id, Folder.path == old_path)
        .values(path=new_path, updated_at=ts)
    )
    # Child folder rows (old_path/...).
    result = await session.execute(
        select(Folder).where(
            Folder.owner_id == owner_id,
            Folder.path.like(old_path + "/%"),
        )
    )
    for folder in result.scalars().all():
        folder.path = new_path + folder.path[len(old_path):]
        folder.updated_at = ts

    # Notes at the exact folder path.
    await session.execute(
        update(Note)
        .where(Note.owner_id == owner_id, Note.folder_path == old_path)
        .values(folder_path=new_path, updated_at=ts)
    )
    # Notes inside child paths.
    result = await session.execute(
        select(Note).where(
            Note.owner_id == owner_id,
            Note.folder_path.like(old_path + "/%"),
        )
    )
    for note in result.scalars().all():
        note.folder_path = new_path + note.folder_path[len(old_path):]
        note.updated_at = ts

    await session.flush()


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
