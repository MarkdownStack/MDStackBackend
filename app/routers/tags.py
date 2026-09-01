from fastapi import APIRouter, Depends

from ..database import notes_collection
from ..dependencies import get_current_user
from ..utils import normalize_folder_path  # noqa: F401 (kept for symmetry/future use)

router = APIRouter(prefix="/api/tags", tags=["tags"])


@router.get("")
async def list_tags(current_user: dict = Depends(get_current_user)):
    owner_id = str(current_user["_id"])
    pipeline = [
        {"$match": {"owner_id": owner_id}},
        {"$unwind": "$tags"},
        {"$group": {"_id": "$tags", "count": {"$sum": 1}}},
        {"$sort": {"count": -1, "_id": 1}},
    ]
    results = [{"tag": doc["_id"], "count": doc["count"]} async for doc in notes_collection.aggregate(pipeline)]
    return results


@router.get("/{tag}")
async def notes_with_tag(tag: str, current_user: dict = Depends(get_current_user)):
    owner_id = str(current_user["_id"])
    cursor = notes_collection.find(
        {"tags": tag, "owner_id": owner_id}, {"title": 1, "folder_path": 1, "tags": 1, "updated_at": 1}
    )
    return [
        {
            "id": str(doc["_id"]),
            "title": doc["title"],
            "folder_path": doc.get("folder_path", ""),
            "tags": doc.get("tags", []),
            "updated_at": doc.get("updated_at", ""),
        }
        async for doc in cursor
    ]
