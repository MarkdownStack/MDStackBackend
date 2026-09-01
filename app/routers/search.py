from fastapi import APIRouter, Depends, Query

from ..database import notes_collection
from ..dependencies import get_current_user

router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("")
async def search_notes(q: str = Query(..., min_length=1), current_user: dict = Depends(get_current_user)):
    owner_id = str(current_user["_id"])
    cursor = notes_collection.find(
        {"$text": {"$search": q}, "owner_id": owner_id},
        {"score": {"$meta": "textScore"}, "title": 1, "folder_path": 1, "tags": 1, "content": 1},
    ).sort([("score", {"$meta": "textScore"})]).limit(30)

    results = []
    async for doc in cursor:
        content = doc.get("content", "")
        idx = content.lower().find(q.lower())
        snippet = content[max(0, idx - 40): idx + 80] if idx != -1 else content[:120]
        results.append({
            "id": str(doc["_id"]),
            "title": doc["title"],
            "folder_path": doc.get("folder_path", ""),
            "tags": doc.get("tags", []),
            "snippet": snippet.strip(),
        })
    return results
