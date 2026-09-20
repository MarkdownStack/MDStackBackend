"""ORM object -> response schema mapping for comments."""

from ...db.models import Comment
from ...shared.datetime import iso
from .schemas import CommentOut


def to_comment_out(comment: Comment, author: str) -> CommentOut:
    return CommentOut(
        id=str(comment.id),
        note_id=str(comment.note_id),
        author=author,
        content=comment.content,
        upvotes=comment.upvotes,
        created_at=iso(comment.created_at),
        updated_at=iso(comment.updated_at),
    )
