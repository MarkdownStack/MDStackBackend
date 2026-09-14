"""Business logic for /api/search — moved from app/routers/search.py.

Thin module: search has no collection or schemas of its own, it's a
read-view over notes_collection — see modules/notes/repository.py's
text_search()."""

from ...modules.notes.repository import text_search


async def search_notes(owner_id: str, q: str) -> list[dict]:
    docs = await text_search(owner_id, q, limit=30)

    results = []
    for doc in docs:
        content = doc.get("content", "")
        idx = content.lower().find(q.lower())
        snippet = content[max(0, idx - 40) : idx + 80] if idx != -1 else content[:120]
        results.append(
            {
                "id": str(doc["_id"]),
                "title": doc["title"],
                "folder_path": doc.get("folder_path", ""),
                "tags": doc.get("tags", []),
                "snippet": snippet.strip(),
            }
        )
    return results
