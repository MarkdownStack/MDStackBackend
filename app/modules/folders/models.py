"""Mongo document -> response schema mapping for folders."""

from .schemas import FolderOut


def to_folder_out(doc: dict, default_ts: str) -> FolderOut:
    return FolderOut(
        id=str(doc["_id"]),
        path=doc["path"],
        is_public=doc.get("is_public", False),
        created_at=doc.get("created_at", default_ts),
        updated_at=doc.get("updated_at", default_ts),
    )
