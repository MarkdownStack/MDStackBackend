"""All Motor calls for the notes collection — moved from
app/routers/notes.py (queries) and app/database.py (collection handle)."""

from bson import ObjectId

from ...db.collections import notes_collection


async def find_by_title(owner_id: str, title: str) -> dict | None:
    return await notes_collection.find_one({"title": title, "owner_id": owner_id})


async def find_by_title_excluding(owner_id: str, title: str, exclude_oid: ObjectId) -> dict | None:
    return await notes_collection.find_one({"title": title, "owner_id": owner_id, "_id": {"$ne": exclude_oid}})


async def find_by_id(owner_id: str, note_oid: ObjectId) -> dict | None:
    return await notes_collection.find_one({"_id": note_oid, "owner_id": owner_id})


async def find_by_id_with_backlinks(owner_id: str, note_oid: ObjectId) -> dict | None:
    """Fetching the note and then resolving its backlinks used to be two
    *sequential* round trips to MongoDB — the second couldn't even start
    until the first returned the title. Against a remote/cloud cluster
    (see MONGO_URL in core/config.py), each round trip's network latency
    stacks on top of the other, and this was the main source of the extra
    delay noticed when switching between notes. Folding both into one
    $lookup aggregation resolves the note and its backlinks server-side in
    a single request instead. Returns the note doc with an extra
    "_backlink_docs" key, or None if not found."""
    pipeline = [
        {"$match": {"_id": note_oid, "owner_id": owner_id}},
        {
            "$lookup": {
                "from": "notes",
                "let": {"myTitle": "$title", "myId": "$_id"},
                "pipeline": [
                    {
                        "$match": {
                            "$expr": {
                                "$and": [
                                    {"$eq": ["$owner_id", owner_id]},
                                    {"$ne": ["$_id", "$$myId"]},
                                    {"$in": ["$$myTitle", {"$ifNull": ["$links", []]}]},
                                ]
                            }
                        }
                    },
                    {"$project": {"title": 1}},
                ],
                "as": "_backlink_docs",
            }
        },
    ]
    results = await notes_collection.aggregate(pipeline).to_list(length=1)
    return results[0] if results else None


async def find_titles_linking_to(owner_id: str, title: str, exclude_id: str | None = None) -> list[dict]:
    """Find all of this user's notes whose `links` array contains this note's title."""
    query = {"owner_id": owner_id, "links": title}
    if exclude_id:
        query["_id"] = {"$ne": ObjectId(exclude_id)}
    cursor = notes_collection.find(query, {"title": 1})
    return [{"id": str(doc["_id"]), "title": doc["title"]} async for doc in cursor]


async def list_by_owner(owner_id: str, folder_path: str | None) -> list[dict]:
    query = {"owner_id": owner_id}
    if folder_path is not None:
        query["folder_path"] = folder_path
    cursor = notes_collection.find(query).sort("updated_at", -1)
    return [doc async for doc in cursor]


async def list_published_by_owner(owner_id: str) -> list[dict]:
    # Same card shape/sort as the anonymous Explore feed in modules/public —
    # see service.py's list_my_published_notes for why.
    cursor = notes_collection.find({"owner_id": owner_id, "is_public": True}).sort(
        [("upvotes", -1), ("updated_at", -1)]
    )
    return [doc async for doc in cursor]


async def insert(doc: dict) -> ObjectId:
    result = await notes_collection.insert_one(doc)
    return result.inserted_id


async def update(owner_id: str, note_oid: ObjectId, update_fields: dict) -> None:
    await notes_collection.update_one({"_id": note_oid, "owner_id": owner_id}, {"$set": update_fields})


async def delete(owner_id: str, note_oid: ObjectId) -> int:
    result = await notes_collection.delete_one({"_id": note_oid, "owner_id": owner_id})
    return result.deleted_count


# ---------------------------------------------------------------------------
# Queries for modules/search and modules/tags — both are thin modules with
# no collection of their own (see PLAN.md), so they call straight into this
# repository rather than duplicating notes_collection access.
# ---------------------------------------------------------------------------


async def text_search(owner_id: str, q: str, limit: int = 30) -> list[dict]:
    cursor = (
        notes_collection.find(
            {"$text": {"$search": q}, "owner_id": owner_id},
            {"score": {"$meta": "textScore"}, "title": 1, "folder_path": 1, "tags": 1, "content": 1},
        )
        .sort([("score", {"$meta": "textScore"})])
        .limit(limit)
    )
    return [doc async for doc in cursor]


async def tag_counts(owner_id: str) -> list[dict]:
    pipeline = [
        {"$match": {"owner_id": owner_id}},
        {"$unwind": "$tags"},
        {"$group": {"_id": "$tags", "count": {"$sum": 1}}},
        {"$sort": {"count": -1, "_id": 1}},
    ]
    return [doc async for doc in notes_collection.aggregate(pipeline)]


async def list_by_tag(owner_id: str, tag: str) -> list[dict]:
    cursor = notes_collection.find(
        {"tags": tag, "owner_id": owner_id}, {"title": 1, "folder_path": 1, "tags": 1, "updated_at": 1}
    )
    return [doc async for doc in cursor]
