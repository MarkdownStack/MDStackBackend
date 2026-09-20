"""Business logic for comments on published notes. Posting a comment
requires an account (resolved author — no anonymous spoofing);
reading/upvoting stay open to everyone, same as reading the note itself.

Depends on modules/public for the "is this note actually published" gate
(get_public_note_or_404) — a comment always hangs off a published note, so
this module calls into public rather than re-implementing that check.
This is a one-way dependency (comments -> public): modules/public never
imports anything from here except, at the repository layer only, the pure
counts_for_notes it needs to render comment counts on note listings.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from ...core.exceptions import NotFoundError
from ...db.models import Comment
from ...modules.public import service as public_service
from ...modules.users.repository import authors_by_owner_id
from ...shared.ids import parse_uuid
from . import repository
from .models import to_comment_out
from .schemas import CommentCreate, CommentOut


async def list_comments(db: AsyncSession, note_id: str) -> list[CommentOut]:
    note = await public_service.get_public_note_or_404(db, note_id)  # 404s if not a published note
    comments = await repository.list_by_note(db, note.id)
    owner_ids = {str(c.owner_id) for c in comments if c.owner_id}
    authors = await authors_by_owner_id(db, owner_ids)
    return [to_comment_out(c, authors.get(str(c.owner_id), "Someone")) for c in comments]


async def create_comment(db: AsyncSession, note_id: str, owner_id: uuid.UUID, payload: CommentCreate) -> CommentOut:
    """The one write endpoint here that requires an account — comments are
    tied to the commenter's real identity (resolved the same way a note's
    author is, from their account email) rather than a free-typed name, so
    there's no anonymous impersonation in a note's comment thread."""
    note = await public_service.get_public_note_or_404(db, note_id)  # 404s if not a published note
    comment = Comment(note_id=note.id, owner_id=owner_id, content=payload.content.strip(), upvotes=0)
    await repository.insert(db, comment)
    owner_id_str = str(owner_id)
    authors = await authors_by_owner_id(db, {owner_id_str})
    return to_comment_out(comment, authors.get(owner_id_str, "Someone"))


async def upvote_comment(db: AsyncSession, note_id: str, comment_id: str) -> CommentOut:
    note = await public_service.get_public_note_or_404(db, note_id)  # 404s if not a published note
    comment_uuid = parse_uuid(comment_id, NotFoundError("Comment not found"))

    updated = await repository.upvote(db, comment_uuid, note.id)
    if not updated:
        raise NotFoundError("Comment not found")
    owner_id_str = str(updated.owner_id)
    authors = await authors_by_owner_id(db, {owner_id_str})
    return to_comment_out(updated, authors.get(owner_id_str, "Someone"))
