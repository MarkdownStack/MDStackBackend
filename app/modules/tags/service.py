"""Business logic for /api/tags.

Thin module: tags have their own table now (see db/models.py's Tag/
note_tags), but no schemas or router-facing model of their own — this is
still a read-view assembled from modules/notes/repository.py's
tag_counts()/list_by_tag(), same as before this migration."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from ...modules.notes.repository import list_by_tag, tag_counts
from ...shared.datetime import iso


async def list_tags(db: AsyncSession, owner_id: uuid.UUID) -> list[dict]:
    return await tag_counts(db, owner_id)


async def notes_with_tag(db: AsyncSession, owner_id: uuid.UUID, tag: str) -> list[dict]:
    notes = await list_by_tag(db, owner_id, tag)
    return [
        {
            "id": str(note.id),
            "title": note.title,
            "folder_path": note.folder_path,
            "tags": sorted(t.name for t in note.tags),
            "updated_at": iso(note.updated_at),
        }
        for note in notes
    ]
