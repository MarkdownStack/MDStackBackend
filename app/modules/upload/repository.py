"""The one Motor call specific to bulk upload that isn't already covered
by reusing modules/notes and modules/folders repository functions (see
service.py)."""

from ...db.collections import folders_collection


async def insert_bare_folder(owner_id: str, path: str) -> None:
    """Matches the original ensure_folder_chain's insert exactly: no
    created_at/updated_at fields — unlike modules.folders.repository.
    insert() (used by POST /api/folders), which always stamps both. Kept
    as its own function rather than reusing that one so upload-created
    folders don't silently start getting timestamp fields they never had
    before."""
    await folders_collection.insert_one({"owner_id": owner_id, "path": path})
