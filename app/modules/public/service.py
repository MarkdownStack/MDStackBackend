"""Business logic for /api/public's note/folder routes — reading published
notes/folders, anonymous voting — moved from app/routers/public.py.
Behavior unchanged; HTTPException replaced with the equivalent domain
exception.

Reading is public everywhere here — no auth check on any read, and a
note's own is_public flag (or a folder's, for the folder-scoped routes) is
the only thing standing between it and the whole internet. The one
exception is posting a comment, which lives in modules/comments and
requires an account — see that module's service.py, which calls
get_public_note_or_404 below to share this exact 404-not-403 gate rather
than re-implementing it.
"""

import re

from ...core.exceptions import NotFoundError
from ...modules.comments.repository import counts_for_notes
from ...modules.folders.repository import count_notes_matching_scope
from ...modules.users.repository import authors_by_owner_id
from ...shared.markdown import excerpt as excerpt_of
from ...shared.objectid import parse_object_id
from ...shared.paths import folder_scope_pattern
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


async def get_public_note_or_404(note_id: str) -> dict:
    """Shared by every route below that needs a published note: 404s
    (rather than 403) whether the note doesn't exist at all, isn't
    published, or note_id isn't even a valid ObjectId — an unpublished
    note must look identical to a nonexistent one from the outside. Also
    called by modules/comments, since a comment always hangs off a
    published note."""
    note_oid = parse_object_id(note_id, NotFoundError("Note not found"))
    doc = await repository.find_public_note(note_oid)
    if not doc:
        raise NotFoundError("Note not found")
    return doc


async def get_public_folder_or_404(folder_id: str) -> dict:
    """Mirrors get_public_note_or_404 above: 404s (never 403) whether the
    folder doesn't exist, isn't published, or folder_id isn't a valid
    ObjectId at all, so an unpublished folder looks identical to a
    nonexistent one from the outside."""
    folder_oid = parse_object_id(folder_id, NotFoundError("Folder not found"))
    doc = await repository.find_public_folder(folder_oid)
    if not doc:
        raise NotFoundError("Folder not found")
    return doc


async def _serialize_public_note(doc: dict) -> PublicNoteOut:
    author = "Someone"
    if doc.get("owner_id"):
        authors = await authors_by_owner_id({doc["owner_id"]})
        author = authors.get(doc["owner_id"], "Someone")
    count = await repository.count_comments_for_note(str(doc["_id"]))
    return to_public_note_out(doc, author, count)


async def list_public_notes(limit: int, current_user_id: str | None) -> list[PublicNoteSummary]:
    # Capped, and sorted by upvotes first (most-recently-updated as the
    # tiebreaker) — this powers the logged-out landing page's "explore" feed
    # across every user's vault, not just one person's. When the caller is
    # logged in (Explore, inside the app shell), their own published notes
    # are excluded — they already know what they've published; this feed is
    # for discovering everyone *else's*.
    limit = max(1, min(limit, 200))
    query = {"is_public": True}
    if current_user_id:
        query["owner_id"] = {"$ne": current_user_id}
    docs = await repository.list_public_notes(query, limit)

    owner_ids = {doc["owner_id"] for doc in docs if doc.get("owner_id")}
    note_ids = [str(doc["_id"]) for doc in docs]
    authors = await authors_by_owner_id(owner_ids)
    counts = await counts_for_notes(note_ids)

    return [
        to_public_note_summary(
            doc,
            authors.get(doc.get("owner_id", ""), "Someone"),
            counts.get(str(doc["_id"]), 0),
            excerpt_of(doc.get("content", "")),
        )
        for doc in docs
    ]


async def get_public_note(note_id: str) -> PublicNoteOut:
    doc = await get_public_note_or_404(note_id)
    return await _serialize_public_note(doc)


async def vote_public_note(note_id: str, payload: VoteUpdate) -> PublicNoteOut:
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
    doc = await get_public_note_or_404(note_id)
    up_delta = (1 if payload.next == 1 else 0) - (1 if payload.previous == 1 else 0)
    down_delta = (1 if payload.next == -1 else 0) - (1 if payload.previous == -1 else 0)

    updated = await repository.vote_note(doc["_id"], up_delta, down_delta)
    return await _serialize_public_note(updated)


async def list_public_folders(limit: int, current_user_id: str | None) -> list[PublicFolderSummary]:
    """Every folder across every vault that's been published as a whole —
    the folder-level counterpart to list_public_notes above, powering the
    logged-in Explore feed and the logged-out front page's "published
    folders" listing. Sorted by most-recently-updated, since a folder
    (unlike a note) has no upvote count of its own to rank by. Same
    owner-exclusion rule as notes: a logged-in caller doesn't see their own
    published folders here — that's what the sidebar's own globe badges are
    for."""
    limit = max(1, min(limit, 200))
    query = {"is_public": True}
    if current_user_id:
        query["owner_id"] = {"$ne": current_user_id}
    docs = await repository.list_public_folders(query, limit)

    owner_ids = {doc["owner_id"] for doc in docs if doc.get("owner_id")}
    authors = await authors_by_owner_id(owner_ids)

    summaries = []
    for doc in docs:
        path = doc["path"]
        count = await count_notes_matching_scope(doc.get("owner_id", ""), folder_scope_pattern(path))
        summaries.append(to_public_folder_summary(doc, authors.get(doc.get("owner_id", ""), "Someone"), count))
    return summaries


async def get_public_folder(folder_id: str) -> PublicFolderOut:
    """Read-only listing of every note inside a published folder, and any
    subfolders under it — enough (title, excerpt, tags) to populate a
    navigation sidebar without pulling every note's full body over the wire
    up front. Full content for any one note comes from
    get_public_folder_note below, fetched on demand as the reader clicks
    around."""
    doc = await get_public_folder_or_404(folder_id)
    owner_id = doc["owner_id"]
    path = doc["path"]
    notes = await repository.list_notes_in_folder(owner_id, folder_scope_pattern(path))

    authors = await authors_by_owner_id({owner_id})
    author = authors.get(owner_id, "Someone")

    note_summaries = [to_public_folder_note_summary(n, excerpt_of(n.get("content", ""))) for n in notes]
    return to_public_folder_out(doc, author, note_summaries)


async def get_public_folder_note(folder_id: str, note_id: str) -> PublicFolderNoteOut:
    """A single note's full content, scoped to a published folder rather
    than the note's own `is_public` flag — see the module docstring above.
    Re-validates the note actually lives inside the published folder's
    subtree on *every* call (not just once, at listing time), so an
    unpublished sibling folder, the folder being unpublished, or the note
    being moved out from under it in between a reader loading the sidebar
    and clicking a note can't be read through a stale link."""
    doc = await get_public_folder_or_404(folder_id)
    owner_id = doc["owner_id"]
    path = doc["path"]
    note_oid = parse_object_id(note_id, NotFoundError("Note not found"))
    note = await repository.find_note_by_owner(owner_id, note_oid)
    if not note:
        raise NotFoundError("Note not found")
    folder_path = note.get("folder_path", "")
    if not re.match(folder_scope_pattern(path), folder_path):
        raise NotFoundError("Note not found")
    return to_public_folder_note_out(note, folder_path)
