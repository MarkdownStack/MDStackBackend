"""Mongo document -> response schema mapping for /api/public.

Each mapper here is pure — the async author-name/comment-count resolution
these need lives in service.py, which resolves them first and then calls
these to assemble the response."""

from .schemas import (
    PublicFolderNoteOut,
    PublicFolderNoteSummary,
    PublicFolderOut,
    PublicFolderSummary,
    PublicNoteOut,
    PublicNoteSummary,
)


def to_public_note_summary(doc: dict, author: str, comment_count: int, excerpt: str) -> PublicNoteSummary:
    return PublicNoteSummary(
        id=str(doc["_id"]),
        title=doc["title"],
        excerpt=excerpt,
        tags=doc.get("tags", []),
        author=author,
        upvotes=doc.get("upvotes", 0),
        downvotes=doc.get("downvotes", 0),
        comment_count=comment_count,
        updated_at=doc.get("updated_at", ""),
    )


def to_public_note_out(doc: dict, author: str, comment_count: int) -> PublicNoteOut:
    return PublicNoteOut(
        id=str(doc["_id"]),
        title=doc["title"],
        content=doc.get("content", ""),
        tags=doc.get("tags", []),
        author=author,
        upvotes=doc.get("upvotes", 0),
        downvotes=doc.get("downvotes", 0),
        comment_count=comment_count,
        updated_at=doc.get("updated_at", ""),
    )


def to_public_folder_note_summary(doc: dict, excerpt: str) -> PublicFolderNoteSummary:
    return PublicFolderNoteSummary(
        id=str(doc["_id"]),
        title=doc["title"],
        folder_path=doc.get("folder_path", ""),
        excerpt=excerpt,
        tags=doc.get("tags", []),
        updated_at=doc.get("updated_at", ""),
    )


def to_public_folder_out(doc: dict, author: str, note_summaries: list[PublicFolderNoteSummary]) -> PublicFolderOut:
    path = doc["path"]
    return PublicFolderOut(
        id=str(doc["_id"]),
        name=path.split("/")[-1],
        path=path,
        author=author,
        notes=note_summaries,
        updated_at=doc.get("updated_at", ""),
    )


def to_public_folder_summary(doc: dict, author: str, note_count: int) -> PublicFolderSummary:
    path = doc["path"]
    return PublicFolderSummary(
        id=str(doc["_id"]),
        name=path.split("/")[-1],
        path=path,
        author=author,
        note_count=note_count,
        updated_at=doc.get("updated_at", ""),
    )


def to_public_folder_note_out(doc: dict, folder_path: str) -> PublicFolderNoteOut:
    return PublicFolderNoteOut(
        id=str(doc["_id"]),
        title=doc["title"],
        content=doc.get("content", ""),
        folder_path=folder_path,
        tags=doc.get("tags", []),
        updated_at=doc.get("updated_at", ""),
    )
