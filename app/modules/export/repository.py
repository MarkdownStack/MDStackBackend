"""Queries for /api/export.

Talks to the notes/folders tables directly rather than reusing
modules/notes or modules/folders repository functions: export's queries
(an arbitrary union of folder-subtree scopes, or a bare owner_id match for
"all") don't match any existing function's shape in either module, so
reusing would mean adding an export-specific function to a module it
doesn't belong to."""

import uuid

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ...db.models import Folder, Note
from ...shared.paths import folder_scope_clause


async def find_notes(session: AsyncSession, owner_id: uuid.UUID, selected_paths: list[str] | None) -> list[Note]:
    """`selected_paths=None` means "the whole vault"; otherwise every note
    in any of the selected folders' subtrees (each one scoped the same way
    the recursive folder-delete is — see shared/paths.folder_scope_clause)."""
    query = select(Note).options(selectinload(Note.tags)).where(Note.owner_id == owner_id)
    if selected_paths is not None:
        query = query.where(or_(*[folder_scope_clause(Note.folder_path, p) for p in selected_paths]))
    result = await session.execute(query)
    return list(result.scalars().all())


async def find_folders(session: AsyncSession, owner_id: uuid.UUID, selected_paths: list[str] | None) -> list[Folder]:
    query = select(Folder).where(Folder.owner_id == owner_id)
    if selected_paths is not None:
        query = query.where(or_(*[folder_scope_clause(Folder.path, p) for p in selected_paths]))
    result = await session.execute(query)
    return list(result.scalars().all())
