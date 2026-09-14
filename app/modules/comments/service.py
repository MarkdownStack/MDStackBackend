"""Business logic for comments on published notes — moved from
app/routers/public.py. Posting a comment requires an account (resolved
author — no anonymous spoofing); reading/upvoting stay open to everyone,
same as reading the note itself.

Depends on modules/public for the "is this note actually published" gate
(get_public_note_or_404) — a comment always hangs off a published note, so
this module calls into public rather than re-implementing that check.
This is a one-way dependency (comments -> public): modules/public never
imports anything from here except, at the repository layer only, the pure
counts_for_notes/count-related data access it needs to render comment
counts on note listings — see modules/public/repository.py's own note on
why that doesn't create a cycle.
"""

from ...core.exceptions import NotFoundError
from ...modules.public import service as public_service
from ...modules.users.repository import authors_by_owner_id
from ...shared.datetime import now_iso
from ...shared.objectid import parse_object_id
from . import repository
from .models import to_comment_out
from .schemas import CommentCreate, CommentOut


async def list_comments(note_id: str) -> list[CommentOut]:
    await public_service.get_public_note_or_404(note_id)  # 404s if not a published note
    docs = await repository.list_by_note(note_id)
    owner_ids = {d["owner_id"] for d in docs if d.get("owner_id")}
    authors = await authors_by_owner_id(owner_ids)
    return [to_comment_out(d, authors.get(d.get("owner_id", ""), "Someone")) for d in docs]


async def create_comment(note_id: str, owner_id: str, payload: CommentCreate) -> CommentOut:
    """The one write endpoint here that requires an account — comments are
    tied to the commenter's real identity (resolved the same way a note's
    author is, from their account email) rather than a free-typed name, so
    there's no anonymous impersonation in a note's comment thread."""
    await public_service.get_public_note_or_404(note_id)  # 404s if not a published note
    ts = now_iso()
    doc = {
        "note_id": note_id,
        "owner_id": owner_id,
        "content": payload.content.strip(),
        "upvotes": 0,
        "created_at": ts,
        "updated_at": ts,
    }
    comment_id = await repository.insert(doc)
    doc["_id"] = comment_id
    authors = await authors_by_owner_id({owner_id})
    return to_comment_out(doc, authors.get(owner_id, "Someone"))


async def upvote_comment(note_id: str, comment_id: str) -> CommentOut:
    await public_service.get_public_note_or_404(note_id)  # 404s if not a published note
    comment_oid = parse_object_id(comment_id, NotFoundError("Comment not found"))

    updated = await repository.upvote(comment_oid, note_id)
    if not updated:
        raise NotFoundError("Comment not found")
    authors = await authors_by_owner_id({updated.get("owner_id", "")})
    return to_comment_out(updated, authors.get(updated.get("owner_id", ""), "Someone"))
