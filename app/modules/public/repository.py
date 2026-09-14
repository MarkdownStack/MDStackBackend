"""All Motor calls the /api/public note/folder routes need — moved from
app/routers/public.py (queries) and app/database.py (collection handles).

count_comments_for_note below is the one exception to "comments belong to
modules/comments": it's the exact single-note count the original code ran
directly against comments_collection (not through any comments
abstraction), kept here rather than imported from modules/comments so this
module and modules/comments don't end up needing each other's service
layer — see modules/comments/service.py's own note on the one-way
dependency this keeps (comments -> public, never the reverse).
"""

from bson import ObjectId
from pymongo import ReturnDocument

from ...db.collections import comments_collection, folders_collection, notes_collection


async def find_public_note(note_oid: ObjectId) -> dict | None:
    return await notes_collection.find_one({"_id": note_oid, "is_public": True})


async def find_public_folder(folder_oid: ObjectId) -> dict | None:
    return await folders_collection.find_one({"_id": folder_oid, "is_public": True})


async def count_comments_for_note(note_id: str) -> int:
    return await comments_collection.count_documents({"note_id": note_id})


async def list_public_notes(query: dict, limit: int) -> list[dict]:
    cursor = notes_collection.find(query).sort([("upvotes", -1), ("updated_at", -1)]).limit(limit)
    return [doc async for doc in cursor]


async def vote_note(note_oid: ObjectId, up_delta: int, down_delta: int) -> dict:
    return await notes_collection.find_one_and_update(
        {"_id": note_oid},
        [
            {
                "$set": {
                    "upvotes": {"$max": [0, {"$add": [{"$ifNull": ["$upvotes", 0]}, up_delta]}]},
                    "downvotes": {"$max": [0, {"$add": [{"$ifNull": ["$downvotes", 0]}, down_delta]}]},
                }
            }
        ],
        return_document=ReturnDocument.AFTER,
    )


async def list_public_folders(query: dict, limit: int) -> list[dict]:
    cursor = folders_collection.find(query).sort("updated_at", -1).limit(limit)
    return [doc async for doc in cursor]


async def list_notes_in_folder(owner_id: str, pattern: str) -> list[dict]:
    cursor = notes_collection.find({"owner_id": owner_id, "folder_path": {"$regex": pattern}}).sort(
        [("folder_path", 1), ("title", 1)]
    )
    return [doc async for doc in cursor]


async def find_note_by_owner(owner_id: str, note_oid: ObjectId) -> dict | None:
    return await notes_collection.find_one({"_id": note_oid, "owner_id": owner_id})
