"""All Motor calls for the comments collection — moved from
app/routers/public.py (queries) and app/utils.py's comment_counts (the
batch aggregation, now counts_for_notes below)."""

from bson import ObjectId
from pymongo import ReturnDocument

from ...db.collections import comments_collection


async def list_by_note(note_id: str) -> list[dict]:
    cursor = comments_collection.find({"note_id": note_id}).sort("created_at", 1)
    return [doc async for doc in cursor]


async def insert(doc: dict) -> ObjectId:
    result = await comments_collection.insert_one(doc)
    return result.inserted_id


async def upvote(comment_oid: ObjectId, note_id: str) -> dict | None:
    return await comments_collection.find_one_and_update(
        {"_id": comment_oid, "note_id": note_id},
        {"$inc": {"upvotes": 1}},
        return_document=ReturnDocument.AFTER,
    )


async def counts_for_notes(note_ids: list) -> dict:
    """Batch note_id -> comment count in one aggregation, instead of one
    comments_collection round trip per note in a list — used by the
    anonymous Explore feed (modules/public) and "my published notes"
    (modules/notes) so both render comment counts identically."""
    if not note_ids:
        return {}
    pipeline = [
        {"$match": {"note_id": {"$in": note_ids}}},
        {"$group": {"_id": "$note_id", "count": {"$sum": 1}}},
    ]
    return {doc["_id"]: doc["count"] async for doc in comments_collection.aggregate(pipeline)}
