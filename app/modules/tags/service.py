"""Business logic for /api/tags — moved from app/routers/tags.py.

Thin module: tags have no collection or schemas of their own, they're a
read-view over notes_collection — see modules/notes/repository.py's
tag_counts()/list_by_tag()."""

from ...modules.notes.repository import list_by_tag, tag_counts


async def list_tags(owner_id: str) -> list[dict]:
    docs = await tag_counts(owner_id)
    return [{"tag": doc["_id"], "count": doc["count"]} for doc in docs]


async def notes_with_tag(owner_id: str, tag: str) -> list[dict]:
    docs = await list_by_tag(owner_id, tag)
    return [
        {
            "id": str(doc["_id"]),
            "title": doc["title"],
            "folder_path": doc.get("folder_path", ""),
            "tags": doc.get("tags", []),
            "updated_at": doc.get("updated_at", ""),
        }
        for doc in docs
    ]
