"""Business logic for private notes CRUD, backlinks, and the "my published
notes" listing — moved from app/routers/notes.py. Behavior unchanged;
HTTPException is replaced with the equivalent domain exception from
core/exceptions.py (same status code, same detail text)."""

from bson import ObjectId

from ...core.exceptions import BadRequestError, ConflictError, NotFoundError
from ...models import PublicNoteSummary
from ...modules.users.repository import authors_by_owner_id
from ...shared.datetime import now_iso
from ...shared.markdown import excerpt, extract_links, extract_tags
from ...shared.objectid import parse_object_id
from ...shared.paths import normalize_folder_path
from ...utils import comment_counts
from . import repository
from .models import to_note_out, to_note_summary
from .schemas import NoteCreate, NoteOut, NoteSummary, NoteUpdate


def oid(id_str: str) -> ObjectId:
    return parse_object_id(id_str, BadRequestError("Invalid note id"))


async def list_notes(owner_id: str, folder_path: str | None) -> list[NoteSummary]:
    normalized = normalize_folder_path(folder_path) if folder_path is not None else None
    docs = await repository.list_by_owner(owner_id, normalized)
    return [to_note_summary(doc) for doc in docs]


async def list_my_published_notes(owner_id: str) -> list[PublicNoteSummary]:
    # Same card shape (PublicNoteSummary) and same upvotes-first sort as the
    # anonymous Explore feed in modules/public, deliberately — the frontend
    # reuses the exact same grid component for both, pointed at /note/:id
    # (editable) here instead of the read-only /explore/:id, since you
    # already own every note this returns.
    docs = await repository.list_published_by_owner(owner_id)

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


async def get_note(owner_id: str, note_id: str) -> NoteOut:
    note_oid = oid(note_id)
    doc = await repository.find_by_id_with_backlinks(owner_id, note_oid)
    if not doc:
        raise NotFoundError("Note not found")
    backlinks = [{"id": str(b["_id"]), "title": b["title"]} for b in doc.get("_backlink_docs", [])]
    return to_note_out(doc, backlinks)


async def create_note(owner_id: str, payload: NoteCreate) -> NoteOut:
    if await repository.find_by_title(owner_id, payload.title):
        raise ConflictError("A note with this title already exists")

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
    note_id = await repository.insert(doc)
    doc["_id"] = note_id
    backlinks = await repository.find_titles_linking_to(owner_id, doc["title"], exclude_id=str(note_id))
    return to_note_out(doc, backlinks)


async def update_note(owner_id: str, note_id: str, payload: NoteUpdate) -> NoteOut:
    note_oid = oid(note_id)
    doc = await repository.find_by_id(owner_id, note_oid)
    if not doc:
        raise NotFoundError("Note not found")

    update_fields = {}
    if payload.title is not None and payload.title != doc["title"]:
        clash = await repository.find_by_title_excluding(owner_id, payload.title, note_oid)
        if clash:
            raise ConflictError("A note with this title already exists")
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
        await repository.update(owner_id, note_oid, update_fields)

    fresh = await repository.find_by_id(owner_id, note_oid)
    backlinks = await repository.find_titles_linking_to(owner_id, fresh["title"], exclude_id=note_id)
    return to_note_out(fresh, backlinks)


async def delete_note(owner_id: str, note_id: str) -> None:
    note_oid = oid(note_id)
    deleted_count = await repository.delete(owner_id, note_oid)
    if deleted_count == 0:
        raise NotFoundError("Note not found")
