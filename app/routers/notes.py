from fastapi import APIRouter, Depends, HTTPException
from bson import ObjectId
from bson.errors import InvalidId
from typing import List

from ..database import notes_collection
from ..dependencies import get_current_user
from ..models import NoteCreate, NoteUpdate, NoteOut, NoteSummary, PublicNoteSummary, now_iso
from ..utils import extract_links, extract_tags, normalize_folder_path, excerpt, authors_by_owner_id, comment_counts

router = APIRouter(prefix="/api/notes", tags=["notes"])


def oid(id_str: str) -> ObjectId:
    try:
        return ObjectId(id_str)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid note id")


async def resolve_backlinks(owner_id: str, title: str, exclude_id: str | None = None) -> list[dict]:
    """Find all of this user's notes whose `links` array contains this note's title."""
    query = {"owner_id": owner_id, "links": title}
    if exclude_id:
        query["_id"] = {"$ne": ObjectId(exclude_id)}
    cursor = notes_collection.find(query, {"title": 1})
    return [{"id": str(doc["_id"]), "title": doc["title"]} async for doc in cursor]


def doc_to_summary(doc) -> NoteSummary:
    return NoteSummary(
        id=str(doc["_id"]),
        title=doc["title"],
        folder_path=doc.get("folder_path", ""),
        tags=doc.get("tags", []),
        is_public=doc.get("is_public", False),
        upvotes=doc.get("upvotes", 0),
        downvotes=doc.get("downvotes", 0),
        created_at=doc.get("created_at", ""),
        updated_at=doc.get("updated_at", ""),
    )


@router.get("", response_model=List[NoteSummary])
async def list_notes(folder_path: str | None = None, current_user: dict = Depends(get_current_user)):
    owner_id = str(current_user["_id"])
    query = {"owner_id": owner_id}
    if folder_path is not None:
        query["folder_path"] = normalize_folder_path(folder_path)
    cursor = notes_collection.find(query).sort("updated_at", -1)
    return [doc_to_summary(doc) async for doc in cursor]


@router.get("/published/mine", response_model=List[PublicNoteSummary])
async def list_my_published_notes(current_user: dict = Depends(get_current_user)):
    # Same card shape (PublicNoteSummary) and same upvotes-first sort as the
    # anonymous Explore feed in routers/public.py, deliberately — the
    # frontend reuses the exact same grid component for both, pointed at
    # /note/:id (editable) here instead of the read-only /explore/:id, since
    # you already own every note this returns.
    owner_id = str(current_user["_id"])
    cursor = notes_collection.find({"owner_id": owner_id, "is_public": True}).sort(
        [("upvotes", -1), ("updated_at", -1)]
    )
    docs = [doc async for doc in cursor]

    note_ids = [str(doc["_id"]) for doc in docs]
    authors = await authors_by_owner_id({owner_id})
    author_name = authors.get(owner_id, "Someone")
    counts = await comment_counts(note_ids)

    return [
        PublicNoteSummary(
            id=str(doc["_id"]),
            title=doc["title"],
            excerpt=excerpt(doc.get("content", "")),
            tags=doc.get("tags", []),
            author=author_name,
            upvotes=doc.get("upvotes", 0),
            downvotes=doc.get("downvotes", 0),
            comment_count=counts.get(str(doc["_id"]), 0),
            updated_at=doc.get("updated_at", ""),
        )
        for doc in docs
    ]


@router.get("/{note_id}", response_model=NoteOut)
async def get_note(note_id: str, current_user: dict = Depends(get_current_user)):
    owner_id = str(current_user["_id"])
    note_oid = oid(note_id)

    # Fetching the note and then resolving its backlinks used to be two
    # *sequential* round trips to MongoDB — the second couldn't even start
    # until the first returned the title. Against a remote/cloud cluster
    # (see MONGO_URL in database.py), each round trip's network latency
    # stacks on top of the other, and this was the main source of the extra
    # delay noticed when switching between notes. Folding both into one
    # $lookup aggregation resolves the note and its backlinks server-side
    # in a single request instead.
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
    if not results:
        raise HTTPException(status_code=404, detail="Note not found")
    doc = results[0]
    backlinks = [{"id": str(b["_id"]), "title": b["title"]} for b in doc.get("_backlink_docs", [])]
    return NoteOut(
        id=str(doc["_id"]),
        title=doc["title"],
        content=doc.get("content", ""),
        folder_path=doc.get("folder_path", ""),
        tags=doc.get("tags", []),
        links=doc.get("links", []),
        backlinks=backlinks,
        is_public=doc.get("is_public", False),
        upvotes=doc.get("upvotes", 0),
        downvotes=doc.get("downvotes", 0),
        created_at=doc.get("created_at", ""),
        updated_at=doc.get("updated_at", ""),
    )


@router.post("", response_model=NoteOut, status_code=201)
async def create_note(payload: NoteCreate, current_user: dict = Depends(get_current_user)):
    owner_id = str(current_user["_id"])
    existing = await notes_collection.find_one({"title": payload.title, "owner_id": owner_id})
    if existing:
        raise HTTPException(status_code=409, detail="A note with this title already exists")

    ts = now_iso()
    doc = {
        "owner_id": owner_id,
        "title": payload.title,
        "content": payload.content,
        "folder_path": normalize_folder_path(payload.folder_path),
        "tags": extract_tags(payload.content),
        "links": extract_links(payload.content),
        "is_public": False,
        "upvotes": 0,
        "downvotes": 0,
        "created_at": ts,
        "updated_at": ts,
    }
    result = await notes_collection.insert_one(doc)
    backlinks = await resolve_backlinks(owner_id, doc["title"], exclude_id=str(result.inserted_id))
    response_fields = {k: v for k, v in doc.items() if k != "owner_id"}
    return NoteOut(id=str(result.inserted_id), backlinks=backlinks, **response_fields)


@router.put("/{note_id}", response_model=NoteOut)
async def update_note(note_id: str, payload: NoteUpdate, current_user: dict = Depends(get_current_user)):
    owner_id = str(current_user["_id"])
    doc = await notes_collection.find_one({"_id": oid(note_id), "owner_id": owner_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Note not found")

    update_fields = {}
    if payload.title is not None and payload.title != doc["title"]:
        clash = await notes_collection.find_one(
            {"title": payload.title, "owner_id": owner_id, "_id": {"$ne": oid(note_id)}}
        )
        if clash:
            raise HTTPException(status_code=409, detail="A note with this title already exists")
        update_fields["title"] = payload.title
    if payload.folder_path is not None:
        update_fields["folder_path"] = normalize_folder_path(payload.folder_path)
    if payload.content is not None:
        update_fields["content"] = payload.content
        update_fields["tags"] = extract_tags(payload.content)
        update_fields["links"] = extract_links(payload.content)
    if payload.is_public is not None:
        update_fields["is_public"] = payload.is_public

    if update_fields:
        update_fields["updated_at"] = now_iso()
        await notes_collection.update_one({"_id": oid(note_id), "owner_id": owner_id}, {"$set": update_fields})

    fresh = await notes_collection.find_one({"_id": oid(note_id), "owner_id": owner_id})
    backlinks = await resolve_backlinks(owner_id, fresh["title"], exclude_id=note_id)
    return NoteOut(
        id=str(fresh["_id"]),
        title=fresh["title"],
        content=fresh.get("content", ""),
        folder_path=fresh.get("folder_path", ""),
        tags=fresh.get("tags", []),
        links=fresh.get("links", []),
        backlinks=backlinks,
        is_public=fresh.get("is_public", False),
        upvotes=fresh.get("upvotes", 0),
        downvotes=fresh.get("downvotes", 0),
        created_at=fresh.get("created_at", ""),
        updated_at=fresh.get("updated_at", ""),
    )


@router.delete("/{note_id}", status_code=204)
async def delete_note(note_id: str, current_user: dict = Depends(get_current_user)):
    owner_id = str(current_user["_id"])
    result = await notes_collection.delete_one({"_id": oid(note_id), "owner_id": owner_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Note not found")
    return None
