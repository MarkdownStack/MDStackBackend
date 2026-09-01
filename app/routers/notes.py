from fastapi import APIRouter, Depends, HTTPException
from bson import ObjectId
from bson.errors import InvalidId
from typing import List

from ..database import notes_collection
from ..dependencies import get_current_user
from ..models import NoteCreate, NoteUpdate, NoteOut, NoteSummary, now_iso
from ..utils import extract_links, extract_tags, normalize_folder_path

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


@router.get("/{note_id}", response_model=NoteOut)
async def get_note(note_id: str, current_user: dict = Depends(get_current_user)):
    owner_id = str(current_user["_id"])
    doc = await notes_collection.find_one({"_id": oid(note_id), "owner_id": owner_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Note not found")
    backlinks = await resolve_backlinks(owner_id, doc["title"], exclude_id=note_id)
    return NoteOut(
        id=str(doc["_id"]),
        title=doc["title"],
        content=doc.get("content", ""),
        folder_path=doc.get("folder_path", ""),
        tags=doc.get("tags", []),
        links=doc.get("links", []),
        backlinks=backlinks,
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
