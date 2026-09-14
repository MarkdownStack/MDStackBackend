"""All Motor calls for the folders collection (and the notes_collection
queries folder operations need — cascade delete and published-folder note
counts both scope across both collections at once) — moved from
app/routers/folders.py (queries) and app/database.py (collection
handles)."""

from pymongo import ReturnDocument

from ...db.collections import folders_collection, notes_collection


async def list_explicit_paths(owner_id: str) -> set[str]:
    return {doc["path"] async for doc in folders_collection.find({"owner_id": owner_id}, {"path": 1})}


async def list_implied_paths(owner_id: str) -> set[str]:
    return {
        doc["folder_path"]
        async for doc in notes_collection.find({"owner_id": owner_id}, {"folder_path": 1})
        if doc.get("folder_path")
    }


async def find_by_path(owner_id: str, path: str) -> dict | None:
    return await folders_collection.find_one({"path": path, "owner_id": owner_id})


async def insert(owner_id: str, path: str, ts: str) -> None:
    await folders_collection.insert_one({"path": path, "owner_id": owner_id, "created_at": ts, "updated_at": ts})


async def find_one_folder_matching_scope(owner_id: str, pattern: str) -> dict | None:
    return await folders_collection.find_one({"owner_id": owner_id, "path": {"$regex": pattern}})


async def find_one_note_matching_scope(owner_id: str, pattern: str) -> dict | None:
    return await notes_collection.find_one({"owner_id": owner_id, "folder_path": {"$regex": pattern}})


async def delete_scope(owner_id: str, pattern: str) -> tuple[int, int]:
    """Deletes every note and folder doc in this owner's subtree matching
    `pattern`. Returns (deleted_notes_count, deleted_folders_count)."""
    notes_result = await notes_collection.delete_many({"owner_id": owner_id, "folder_path": {"$regex": pattern}})
    folders_result = await folders_collection.delete_many({"owner_id": owner_id, "path": {"$regex": pattern}})
    return notes_result.deleted_count, folders_result.deleted_count


async def list_published(owner_id: str) -> list[dict]:
    cursor = folders_collection.find({"owner_id": owner_id, "is_public": True}).sort("updated_at", -1)
    return [doc async for doc in cursor]


async def count_notes_matching_scope(owner_id: str, pattern: str) -> int:
    return await notes_collection.count_documents({"owner_id": owner_id, "folder_path": {"$regex": pattern}})


async def upsert_publish(owner_id: str, path: str, is_public: bool, ts: str) -> dict:
    return await folders_collection.find_one_and_update(
        {"path": path, "owner_id": owner_id},
        {
            "$set": {"is_public": is_public, "updated_at": ts},
            "$setOnInsert": {"path": path, "owner_id": owner_id, "created_at": ts},
        },
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
