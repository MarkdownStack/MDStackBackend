"""ORM object -> response schema mapping for /api/public.

Each mapper here is pure — the async author-name/comment-count resolution
these need lives in service.py, which resolves them first and then calls
these to assemble the response."""

from ...db.models import Folder, Note
from ...shared.datetime import iso
from .schemas import (
    PublicFolderNoteOut,
    PublicFolderNoteSummary,
    PublicFolderOut,
    PublicFolderSummary,
    PublicNoteOut,
    PublicNoteSummary,
)


def _tag_names(note: Note) -> list[str]:
    return sorted(tag.name for tag in note.tags)


def to_public_note_summary(note: Note, author: str, comment_count: int, excerpt: str) -> PublicNoteSummary:
    return PublicNoteSummary(
        id=str(note.id),
        title=note.title,
        excerpt=excerpt,
        tags=_tag_names(note),
        author=author,
        upvotes=note.upvotes,
        downvotes=note.downvotes,
        comment_count=comment_count,
        updated_at=iso(note.updated_at),
    )


def to_public_note_out(note: Note, author: str, comment_count: int) -> PublicNoteOut:
    return PublicNoteOut(
        id=str(note.id),
        title=note.title,
        content=note.content,
        tags=_tag_names(note),
        author=author,
        upvotes=note.upvotes,
        downvotes=note.downvotes,
        comment_count=comment_count,
        updated_at=iso(note.updated_at),
    )


def to_public_folder_note_summary(note: Note, excerpt: str) -> PublicFolderNoteSummary:
    return PublicFolderNoteSummary(
        id=str(note.id),
        title=note.title,
        folder_path=note.folder_path,
        excerpt=excerpt,
        tags=_tag_names(note),
        updated_at=iso(note.updated_at),
    )


def to_public_folder_out(folder: Folder, author: str, note_summaries: list[PublicFolderNoteSummary]) -> PublicFolderOut:
    return PublicFolderOut(
        id=str(folder.id),
        name=folder.path.split("/")[-1],
        path=folder.path,
        author=author,
        notes=note_summaries,
        updated_at=iso(folder.updated_at),
    )


def to_public_folder_summary(folder: Folder, author: str, note_count: int) -> PublicFolderSummary:
    return PublicFolderSummary(
        id=str(folder.id),
        name=folder.path.split("/")[-1],
        path=folder.path,
        author=author,
        note_count=note_count,
        updated_at=iso(folder.updated_at),
    )


def to_public_folder_note_out(note: Note, folder_path: str) -> PublicFolderNoteOut:
    return PublicFolderNoteOut(
        id=str(note.id),
        title=note.title,
        content=note.content,
        folder_path=folder_path,
        tags=_tag_names(note),
        updated_at=iso(note.updated_at),
    )
