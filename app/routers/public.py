from fastapi import APIRouter, Depends, HTTPException
from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ReturnDocument
from typing import List

from ..database import notes_collection, comments_collection
from ..dependencies import get_current_user, get_current_user_optional
from ..models import PublicNoteOut, PublicNoteSummary, CommentCreate, CommentOut, VoteUpdate, now_iso
from ..utils import excerpt, authors_by_owner_id, comment_counts

# Reading is public everywhere in this file — no auth dependency on any GET,
# and a note's own is_public flag (checked explicitly in every query below)
# is the only thing standing between it and the whole internet. The one
# deliberate exception is posting a comment, which requires an account (see
# create_comment) so every comment has a real, non-spoofable author.
router = APIRouter(prefix="/api/public", tags=["public"])


async def get_public_note_doc(note_id: str) -> dict:
    """Shared by every route below: 404s (rather than 403) whether the note
    doesn't exist at all, isn't published, or note_id isn't even a valid
    ObjectId — an unpublished note must look identical to a nonexistent one
    from the outside."""
    try:
        note_oid = ObjectId(note_id)
    except InvalidId:
        raise HTTPException(status_code=404, detail="Note not found")
    doc = await notes_collection.find_one({"_id": note_oid, "is_public": True})
    if not doc:
        raise HTTPException(status_code=404, detail="Note not found")
    return doc


async def serialize_public_note(doc: dict) -> PublicNoteOut:
    author = "Someone"
    if doc.get("owner_id"):
        authors = await authors_by_owner_id({doc["owner_id"]})
        author = authors.get(doc["owner_id"], "Someone")
    count = await comments_collection.count_documents({"note_id": str(doc["_id"])})
    return PublicNoteOut(
        id=str(doc["_id"]),
        title=doc["title"],
        content=doc.get("content", ""),
        tags=doc.get("tags", []),
        author=author,
        upvotes=doc.get("upvotes", 0),
        downvotes=doc.get("downvotes", 0),
        comment_count=count,
        updated_at=doc.get("updated_at", ""),
    )


def serialize_comment(doc: dict, author: str) -> CommentOut:
    return CommentOut(
        id=str(doc["_id"]),
        note_id=doc["note_id"],
        author=author,
        content=doc.get("content", ""),
        upvotes=doc.get("upvotes", 0),
        created_at=doc.get("created_at", ""),
        updated_at=doc.get("updated_at", ""),
    )


@router.get("/notes", response_model=List[PublicNoteSummary])
async def list_public_notes(limit: int = 100, current_user: dict | None = Depends(get_current_user_optional)):
    # Capped, and sorted by upvotes first (most-recently-updated as the
    # tiebreaker) — this powers the logged-out landing page's "explore" feed
    # across every user's vault, not just one person's. When the caller is
    # logged in (Explore, inside the app shell), their own published notes
    # are excluded — they already know what they've published; this feed is
    # for discovering everyone *else's*.
    limit = max(1, min(limit, 200))
    query = {"is_public": True}
    if current_user:
        query["owner_id"] = {"$ne": str(current_user["_id"])}
    cursor = notes_collection.find(query).sort(
        [("upvotes", -1), ("updated_at", -1)]
    ).limit(limit)
    docs = [doc async for doc in cursor]

    owner_ids = {doc["owner_id"] for doc in docs if doc.get("owner_id")}
    note_ids = [str(doc["_id"]) for doc in docs]
    authors = await authors_by_owner_id(owner_ids)
    counts = await comment_counts(note_ids)

    return [
        PublicNoteSummary(
            id=str(doc["_id"]),
            title=doc["title"],
            excerpt=excerpt(doc.get("content", "")),
            tags=doc.get("tags", []),
            author=authors.get(doc.get("owner_id", ""), "Someone"),
            upvotes=doc.get("upvotes", 0),
            downvotes=doc.get("downvotes", 0),
            comment_count=counts.get(str(doc["_id"]), 0),
            updated_at=doc.get("updated_at", ""),
        )
        for doc in docs
    ]


@router.get("/notes/{note_id}", response_model=PublicNoteOut)
async def get_public_note(note_id: str):
    doc = await get_public_note_doc(note_id)
    return await serialize_public_note(doc)


@router.post("/notes/{note_id}/vote", response_model=PublicNoteOut)
async def vote_public_note(note_id: str, payload: VoteUpdate):
    """Anonymous like/dislike toggle — no account needed, same as reading the
    note itself. `previous`/`next` are each -1 (downvoted), 0 (no vote), or 1
    (upvoted); the server applies just the delta between them, so e.g.
    switching straight from an upvote to a downvote in one call moves both
    counters correctly instead of needing two round trips.

    There's deliberately no server-side vote *ownership* tracking (that would
    need accounts or IP tracking, neither of which fit a page anyone can read
    with no login) — the frontend remembers each browser's own vote via
    localStorage and reports it back as `previous`. That's a soft deterrent
    against re-voting, not a hard guarantee; treat these counts as a
    "temperature", not a tamper-proof number, unless/until voting requires
    an account."""
    doc = await get_public_note_doc(note_id)
    up_delta = (1 if payload.next == 1 else 0) - (1 if payload.previous == 1 else 0)
    down_delta = (1 if payload.next == -1 else 0) - (1 if payload.previous == -1 else 0)

    updated = await notes_collection.find_one_and_update(
        {"_id": doc["_id"]},
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
    return await serialize_public_note(updated)


@router.get("/notes/{note_id}/comments", response_model=List[CommentOut])
async def list_comments(note_id: str):
    await get_public_note_doc(note_id)  # 404s if not a published note
    cursor = comments_collection.find({"note_id": note_id}).sort("created_at", 1)
    docs = [doc async for doc in cursor]
    owner_ids = {d["owner_id"] for d in docs if d.get("owner_id")}
    authors = await authors_by_owner_id(owner_ids)
    return [serialize_comment(d, authors.get(d.get("owner_id", ""), "Someone")) for d in docs]


@router.post("/notes/{note_id}/comments", response_model=CommentOut, status_code=201)
async def create_comment(note_id: str, payload: CommentCreate, current_user: dict = Depends(get_current_user)):
    """The one write endpoint in this router that requires an account —
    comments are tied to the commenter's real identity (resolved the same
    way a note's author is, from their account email) rather than a
    free-typed name, so there's no anonymous impersonation in a note's
    comment thread."""
    await get_public_note_doc(note_id)  # 404s if not a published note
    owner_id = str(current_user["_id"])
    ts = now_iso()
    doc = {
        "note_id": note_id,
        "owner_id": owner_id,
        "content": payload.content.strip(),
        "upvotes": 0,
        "created_at": ts,
        "updated_at": ts,
    }
    result = await comments_collection.insert_one(doc)
    doc["_id"] = result.inserted_id
    authors = await authors_by_owner_id({owner_id})
    return serialize_comment(doc, authors.get(owner_id, "Someone"))


@router.post("/notes/{note_id}/comments/{comment_id}/upvote", response_model=CommentOut)
async def upvote_comment(note_id: str, comment_id: str):
    await get_public_note_doc(note_id)  # 404s if not a published note
    try:
        comment_oid = ObjectId(comment_id)
    except InvalidId:
        raise HTTPException(status_code=404, detail="Comment not found")

    updated = await comments_collection.find_one_and_update(
        {"_id": comment_oid, "note_id": note_id},
        {"$inc": {"upvotes": 1}},
        return_document=ReturnDocument.AFTER,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Comment not found")
    authors = await authors_by_owner_id({updated.get("owner_id", "")})
    return serialize_comment(updated, authors.get(updated.get("owner_id", ""), "Someone"))
