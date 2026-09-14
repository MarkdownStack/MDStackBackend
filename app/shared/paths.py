"""Pure folder-path helpers — moved from app/utils.py."""

import re


def normalize_folder_path(path: str) -> str:
    path = (path or "").strip().strip("/")
    # collapse duplicate slashes
    parts = [p for p in path.split("/") if p]
    return "/".join(parts)


def folder_scope_pattern(path: str) -> str:
    """Anchored + escaped 'this folder or anything nested under it' regex,
    matching `path` itself and `path/...` but never an unrelated sibling
    that merely starts with the same characters (e.g. "notes" must not also
    match "notes-archive"). Shared by every place that needs to scope a
    query to a folder's whole subtree: the recursive folder-delete and the
    published-folder note-count/listing endpoints (modules/folders,
    modules/public) all use this exact pattern, rather than each
    reimplementing (and risking drifting from) their own version of it."""
    return f"^{re.escape(path)}(/.*)?$"
