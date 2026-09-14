"""Motor calls for /api/export — moved from app/routers/export.py.

Talks to notes_collection/folders_collection directly rather than reusing
modules/notes or modules/folders repository functions: export's queries
(arbitrary $or-of-regex folder scoping, or a bare owner_id match for "all")
don't match any existing function's shape in either module, so reusing
would mean adding an export-specific function to a module it doesn't
belong to."""

from ...db.collections import folders_collection, notes_collection


async def find_notes(query: dict) -> list[dict]:
    return [doc async for doc in notes_collection.find(query)]


async def find_folders(query: dict) -> list[dict]:
    return [doc async for doc in folders_collection.find(query)]
