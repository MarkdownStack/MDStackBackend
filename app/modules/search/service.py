"""Business logic for /api/search.

Thin module: search has no table or schemas of its own, it's a read-view
over notes — see modules/notes/repository.py's text_search(), which now
runs Postgres full-text search instead of Mongo's `$text` index."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from ...modules.notes.repository import text_search


async def search_notes(db: AsyncSession, owner_id: uuid.UUID, q: str) -> list[dict]:
    notes = await text_search(db, owner_id, q, limit=30)

    results = []
    for note in notes:
        content = note.content or ""
        # Plain substring search for the snippet window — same as before
        # this migration, no regex involved either way.
        idx = content.lower().find(q.lower())
        snippet = content[max(0, idx - 40) : idx + 80] if idx != -1 else content[:120]
        results.append(
            {
                "id": str(note.id),
                "title": note.title,
                "folder_path": note.folder_path,
                "tags": sorted(tag.name for tag in note.tags),
                "snippet": snippet.strip(),
            }
        )
    return results
