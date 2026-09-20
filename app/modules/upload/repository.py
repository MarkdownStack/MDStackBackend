"""The one query specific to bulk upload that isn't already covered by
reusing modules/notes and modules/folders repository functions (see
service.py)."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from ...db.models import Folder


async def insert_bare_folder(session: AsyncSession, owner_id: uuid.UUID, path: str) -> None:
    """Matches the original ensure_folder_chain's insert exactly: no
    created_at/updated_at — unlike modules.folders.repository.insert()
    (used by POST /api/folders), which always stamps both. Kept as its own
    function rather than reusing that one so upload-created folders don't
    silently start getting timestamp fields they never had before."""
    session.add(Folder(owner_id=owner_id, path=path))
