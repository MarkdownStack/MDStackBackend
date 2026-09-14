"""Mongo document -> response schema mapping for notes."""

from .schemas import NoteOut, NoteSummary


def to_note_summary(doc: dict) -> NoteSummary:
    return NoteSummary(
        id=str(doc["_id"]),
        title=doc["title"],
        folder_path=doc.get("folder_path", ""),
        tags=doc.get("tags", []),
        is_public=doc.get("is_public", False),
        upvotes=doc.get("upvotes", 0),
        downvotes=doc.get("downvotes", 0),
        created_at=doc.get("created_at", ""),
        updated_at=doc.get("updated_at", ""),
    )


def to_note_out(doc: dict, backlinks: list[dict]) -> NoteOut:
    return NoteOut(
        id=str(doc["_id"]),
        title=doc["title"],
        content=doc.get("content", ""),
        folder_path=doc.get("folder_path", ""),
        tags=doc.get("tags", []),
        links=doc.get("links", []),
        backlinks=backlinks,
        is_public=doc.get("is_public", False),
        upvotes=doc.get("upvotes", 0),
        downvotes=doc.get("downvotes", 0),
        created_at=doc.get("created_at", ""),
        updated_at=doc.get("updated_at", ""),
    )
