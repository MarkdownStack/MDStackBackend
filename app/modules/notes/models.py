"""ORM object -> response schema mapping for notes."""

from ...db.models import Note
from ...shared.datetime import iso
from .schemas import NoteOut, NoteSummary


def _tag_names(note: Note) -> list[str]:
    # Alphabetical, not insertion-order — see db/models.py's note_tags
    # docstring for why that's an acceptable, deliberate difference from
    # the old Mongo array's order.
    return sorted(tag.name for tag in note.tags)


def to_note_summary(note: Note) -> NoteSummary:
    return NoteSummary(
        id=str(note.id),
        title=note.title,
        folder_path=note.folder_path,
        tags=_tag_names(note),
        is_public=note.is_public,
        upvotes=note.upvotes,
        downvotes=note.downvotes,
        created_at=iso(note.created_at),
        updated_at=iso(note.updated_at),
    )


def to_note_out(note: Note, backlinks: list[dict]) -> NoteOut:
    return NoteOut(
        id=str(note.id),
        title=note.title,
        content=note.content,
        folder_path=note.folder_path,
        tags=_tag_names(note),
        links=list(note.links or []),
        backlinks=backlinks,
        is_public=note.is_public,
        upvotes=note.upvotes,
        downvotes=note.downvotes,
        created_at=iso(note.created_at),
        updated_at=iso(note.updated_at),
    )
