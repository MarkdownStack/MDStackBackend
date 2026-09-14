"""Request model for /api/export — moved from app/models.py."""

from typing import List

from pydantic import BaseModel


class ExportRequest(BaseModel):
    # Paths of the folders to include (each one pulls in that folder, every
    # note inside it, and every subfolder underneath it — same "anchored
    # prefix" scoping the recursive folder-delete uses). Ignored entirely
    # when `all` is true. An empty list with `all=False` is a 400, not "export
    # nothing" — the frontend's "All" checkbox is the explicit way to mean
    # the whole vault, so a plain empty selection is treated as a mistake.
    folder_paths: List[str] = []
    all: bool = False
