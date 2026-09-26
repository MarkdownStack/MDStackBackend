"""ORM object -> response schema mapping for comments."""

import uuid

from ...db.models import Comment
from ...shared.datetime import iso
from .schemas import CommentOut


def to_comment_out(comment: Comment, author: str, current_user_id: uuid.UUID | None = None) -> CommentOut:
    return CommentOut(
        id=str(comment.id),
        note_id=str(comment.note_id),
        author=author,
        content=comment.content,
        upvotes=comment.upvotes,
        created_at=iso(comment.created_at),
        updated_at=iso(comment.updated_at),
        is_mine=current_user_id is not None and comment.owner_id == current_user_id,
    )
