"""Business logic for private notes CRUD, backlinks, and the "my
published notes" listing. Behavior unchanged from before this migration;
every DB call now takes the request's `AsyncSession` and ids are
`uuid.UUID`."""

import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from ...core.exceptions import BadRequestError, ConflictError, NotFoundError
from ...modules.comments.repository import counts_for_notes as comment_counts
from ...modules.folders.repository import find_by_path as find_folder_by_path
from ...modules.public.schemas import PublicNoteSummary
from ...modules.users.repository import authors_by_owner_id
from ...shared.datetime import iso
from ...shared.ids import parse_uuid
from ...shared.markdown import excerpt, extract_links, extract_tags
from ...shared.paths import normalize_folder_path
from ...db.models import Note
from . import repository
from .models import to_note_out, to_note_summary
from .schemas import NoteCreate, NoteOut, NoteSummary, NoteUpdate


def oid(id_str: str) -> uuid.UUID:
    return parse_uuid(id_str, BadRequestError("Invalid note id"))


async def _resolve_folder_id(db: AsyncSession, owner_id: uuid.UUID, folder_path: str) -> uuid.UUID | None:
    """A note's folder_id points at a real Folder row when one exists at
    this path, and stays NULL otherwise — folder_path itself (not this FK)
    remains the source of truth for "what folder is this note in", since a
    note can live at a folder_path with no backing Folder row at all (an
    "implied" folder — see db/models.py's Note docstring)."""
    if not folder_path:
        return None
    folder = await find_folder_by_path(db, owner_id, folder_path)
    return folder.id if folder else None


async def list_notes(db: AsyncSession, owner_id: uuid.UUID, folder_path: str | None) -> list[NoteSummary]:
    normalized = normalize_folder_path(folder_path) if folder_path is not None else None
    notes = await repository.list_by_owner(db, owner_id, normalized)
    return [to_note_summary(note) for note in notes]


async def list_my_published_notes(db: AsyncSession, owner_id: uuid.UUID) -> list[PublicNoteSummary]:
    # Same card shape (PublicNoteSummary) and same upvotes-first sort as
    # the anonymous Explore feed in modules/public, deliberately — the
    # frontend reuses the exact same grid component for both.
    notes = await repository.list_published_by_owner(db, owner_id)

    note_ids = [str(note.id) for note in notes]
    owner_id_str = str(owner_id)
    authors = await authors_by_owner_id(db, {owner_id_str})
    author_name = authors.get(owner_id_str, "Someone")
    counts = await comment_counts(db, note_ids)

    return [
        PublicNoteSummary(
            id=str(note.id),
            title=note.title,
            excerpt=excerpt(note.content),
            tags=sorted(tag.name for tag in note.tags),
            author=author_name,
            upvotes=note.upvotes,
            downvotes=note.downvotes,
            comment_count=counts.get(str(note.id), 0),
            updated_at=iso(note.updated_at),
        )
        for note in notes
    ]


async def get_note(db: AsyncSession, owner_id: uuid.UUID, note_id: str) -> NoteOut:
    note_uuid = oid(note_id)
    note = await repository.find_by_id(db, owner_id, note_uuid)
    if not note:
        raise NotFoundError("Note not found")
    backlinks = await repository.find_titles_linking_to(db, owner_id, note.title, exclude_id=note.id)
    return to_note_out(note, backlinks)


async def create_note(db: AsyncSession, owner_id: uuid.UUID, payload: NoteCreate) -> NoteOut:
    if await repository.find_by_title(db, owner_id, payload.title):
        raise ConflictError("A note with this title already exists")

    folder_path = normalize_folder_path(payload.folder_path)
    note = Note(
        owner_id=owner_id,
        title=payload.title,
        content=payload.content,
        folder_path=folder_path,
        folder_id=await _resolve_folder_id(db, owner_id, folder_path),
        links=extract_links(payload.content),
        is_public=False,
        upvotes=0,
        downvotes=0,
    )
    note.tags = await repository.get_or_create_tags(db, owner_id, extract_tags(payload.content))
    await repository.insert(db, note)

    backlinks = await repository.find_titles_linking_to(db, owner_id, note.title, exclude_id=note.id)
    return to_note_out(note, backlinks)


async def update_note(db: AsyncSession, owner_id: uuid.UUID, note_id: str, payload: NoteUpdate) -> NoteOut:
    note_uuid = oid(note_id)
    note = await repository.find_by_id(db, owner_id, note_uuid)
    if not note:
        raise NotFoundError("Note not found")

    if payload.title is not None and payload.title != note.title:
        if await repository.find_by_title_excluding(db, owner_id, payload.title, note_uuid):
            raise ConflictError("A note with this title already exists")
        note.title = payload.title
    if payload.folder_path is not None:
        folder_path = normalize_folder_path(payload.folder_path)
        note.folder_path = folder_path
        note.folder_id = await _resolve_folder_id(db, owner_id, folder_path)
    if payload.content is not None:
        note.content = payload.content
        note.links = extract_links(payload.content)
        note.tags = await repository.get_or_create_tags(db, owner_id, extract_tags(payload.content))
    if payload.is_public is not None:
        note.is_public = payload.is_public

    changed = any(
        f is not None for f in (payload.title, payload.folder_path, payload.content, payload.is_public)
    )
    if changed:
        # Explicit, app-managed bump — see db/models.py's Note.updated_at
        # comment for why this isn't a server-side onupdate trigger.
        note.updated_at = datetime.now(timezone.utc)

    await db.flush()

    backlinks = await repository.find_titles_linking_to(db, owner_id, note.title, exclude_id=note.id)
    return to_note_out(note, backlinks)


async def delete_note(db: AsyncSession, owner_id: uuid.UUID, note_id: str) -> None:
    note_uuid = oid(note_id)
    deleted_count = await repository.delete(db, owner_id, note_uuid)
    if deleted_count == 0:
        raise NotFoundError("Note not found")
