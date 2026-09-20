"""Business logic for /api/public's note/folder routes — reading published
notes/folders, anonymous voting. Behavior unchanged from before this
migration; every DB call now takes the request's `AsyncSession` and ids
are `uuid.UUID`.

Reading is public everywhere here — no auth check on any read, and a
note's own is_public flag (or a folder's, for the folder-scoped routes) is
the only thing standing between it and the whole internet. The one
exception is posting a comment, which lives in modules/comments and
requires an account — see that module's service.py, which calls
get_public_note_or_404 below to share this exact 404-not-403 gate rather
than re-implementing it.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from ...core.exceptions import NotFoundError
from ...db.models import Note
from ...modules.comments.repository import counts_for_notes
from ...modules.folders.repository import count_notes_matching_scope
from ...modules.users.repository import authors_by_owner_id
from ...shared.ids import parse_uuid
from ...shared.markdown import excerpt as excerpt_of
from ...shared.paths import path_in_scope
from . import repository
from .models import (
    to_public_folder_note_out,
    to_public_folder_note_summary,
    to_public_folder_out,
    to_public_folder_summary,
    to_public_note_out,
    to_public_note_summary,
)
from .schemas import (
    PublicFolderNoteOut,
    PublicFolderOut,
    PublicFolderSummary,
    PublicNoteOut,
    PublicNoteSummary,
    VoteUpdate,
)


async def get_public_note_or_404(db: AsyncSession, note_id: str) -> Note:
    """Shared by every route below that needs a published note: 404s
    (rather than 403) whether the note doesn't exist at all, isn't
    published, or note_id isn't even a valid id — an unpublished note must
    look identical to a nonexistent one from the outside. Also called by
    modules/comments, since a comment always hangs off a published note."""
    note_uuid = parse_uuid(note_id, NotFoundError("Note not found"))
    note = await repository.find_public_note(db, note_uuid)
    if not note:
        raise NotFoundError("Note not found")
    return note


async def get_public_folder_or_404(db: AsyncSession, folder_id: str):
    """Mirrors get_public_note_or_404 above: 404s (never 403) whether the
    folder doesn't exist, isn't published, or folder_id isn't a valid id
    at all, so an unpublished folder looks identical to a nonexistent one
    from the outside."""
    folder_uuid = parse_uuid(folder_id, NotFoundError("Folder not found"))
    folder = await repository.find_public_folder(db, folder_uuid)
    if not folder:
        raise NotFoundError("Folder not found")
    return folder


async def _serialize_public_note(db: AsyncSession, note: Note) -> PublicNoteOut:
    author = "Someone"
    owner_id_str = str(note.owner_id)
    authors = await authors_by_owner_id(db, {owner_id_str})
    author = authors.get(owner_id_str, "Someone")
    count = await repository.count_comments_for_note(db, note.id)
    return to_public_note_out(note, author, count)


async def list_public_notes(db: AsyncSession, limit: int, current_user_id: uuid.UUID | None) -> list[PublicNoteSummary]:
    # Capped, and sorted by upvotes first (most-recently-updated as the
    # tiebreaker) — this powers the logged-out landing page's "explore"
    # feed across every user's vault, not just one person's. When the
    # caller is logged in, their own published notes are excluded.
    limit = max(1, min(limit, 200))
    notes = await repository.list_public_notes(db, current_user_id, limit)

    owner_ids = {str(n.owner_id) for n in notes}
    note_ids = [str(n.id) for n in notes]
    authors = await authors_by_owner_id(db, owner_ids)
    counts = await counts_for_notes(db, note_ids)

    return [
        to_public_note_summary(
            note,
            authors.get(str(note.owner_id), "Someone"),
            counts.get(str(note.id), 0),
            excerpt_of(note.content),
        )
        for note in notes
    ]


async def get_public_note(db: AsyncSession, note_id: str) -> PublicNoteOut:
    note = await get_public_note_or_404(db, note_id)
    return await _serialize_public_note(db, note)


async def vote_public_note(db: AsyncSession, note_id: str, payload: VoteUpdate) -> PublicNoteOut:
    """Anonymous like/dislike toggle — no account needed, same as reading
    the note itself. See the old service.py's docstring for the full
    "temperature, not a tamper-proof number" rationale — unchanged by this
    migration, `func.greatest(0, ...)` on the Postgres side replaces the
    Mongo aggregation pipeline's `$max` clamp."""
    note = await get_public_note_or_404(db, note_id)
    up_delta = (1 if payload.next == 1 else 0) - (1 if payload.previous == 1 else 0)
    down_delta = (1 if payload.next == -1 else 0) - (1 if payload.previous == -1 else 0)

    updated = await repository.vote_note(db, note.id, up_delta, down_delta)
    return await _serialize_public_note(db, updated)


async def list_public_folders(
    db: AsyncSession, limit: int, current_user_id: uuid.UUID | None
) -> list[PublicFolderSummary]:
    """Every folder across every vault that's been published as a whole —
    the folder-level counterpart to list_public_notes above."""
    limit = max(1, min(limit, 200))
    folders = await repository.list_public_folders(db, current_user_id, limit)

    owner_ids = {str(f.owner_id) for f in folders}
    authors = await authors_by_owner_id(db, owner_ids)

    summaries = []
    for folder in folders:
        count = await count_notes_matching_scope(db, folder.owner_id, folder.path)
        summaries.append(to_public_folder_summary(folder, authors.get(str(folder.owner_id), "Someone"), count))
    return summaries


async def get_public_folder(db: AsyncSession, folder_id: str) -> PublicFolderOut:
    """Read-only listing of every note inside a published folder, and any
    subfolders under it."""
    folder = await get_public_folder_or_404(db, folder_id)
    notes = await repository.list_notes_in_folder(db, folder.owner_id, folder.path)

    owner_id_str = str(folder.owner_id)
    authors = await authors_by_owner_id(db, {owner_id_str})
    author = authors.get(owner_id_str, "Someone")

    note_summaries = [to_public_folder_note_summary(n, excerpt_of(n.content)) for n in notes]
    return to_public_folder_out(folder, author, note_summaries)


async def get_public_folder_note(db: AsyncSession, folder_id: str, note_id: str) -> PublicFolderNoteOut:
    """A single note's full content, scoped to a published folder rather
    than the note's own `is_public` flag. Re-validates the note actually
    lives inside the published folder's subtree on *every* call (not just
    once, at listing time)."""
    folder = await get_public_folder_or_404(db, folder_id)
    note_uuid = parse_uuid(note_id, NotFoundError("Note not found"))
    note = await repository.find_note_by_owner(db, folder.owner_id, note_uuid)
    if not note:
        raise NotFoundError("Note not found")
    if not path_in_scope(note.folder_path, folder.path):
        raise NotFoundError("Note not found")
    return to_public_folder_note_out(note, note.folder_path)
