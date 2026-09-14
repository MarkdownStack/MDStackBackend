"""Mongo document -> response schema mapping for comments — moved from
routers/public.py's serialize_comment()."""

from .schemas import CommentOut


def to_comment_out(doc: dict, author: str) -> CommentOut:
    return CommentOut(
        id=str(doc["_id"]),
        note_id=doc["note_id"],
        author=author,
        content=doc.get("content", ""),
        upvotes=doc.get("upvotes", 0),
        created_at=doc.get("created_at", ""),
        updated_at=doc.get("updated_at", ""),
    )
