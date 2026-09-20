"""ORM object -> response schema mapping for folders."""

from ...db.models import Folder
from ...shared.datetime import iso
from .schemas import FolderOut


def to_folder_out(folder: Folder, default_ts: str) -> FolderOut:
    return FolderOut(
        id=str(folder.id),
        path=folder.path,
        is_public=folder.is_public,
        created_at=iso(folder.created_at, default_ts),
        updated_at=iso(folder.updated_at, default_ts),
    )
