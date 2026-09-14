"""Business logic for /api/upload — moved from app/routers/upload.py.
Reuses modules/notes and modules/folders repository functions rather than
duplicating notes_collection/folders_collection access wherever an
identical query already exists there."""

import os

from ...modules.folders.repository import find_by_path
from ...modules.notes.repository import find_by_title
from ...modules.notes.repository import insert as insert_note
from ...shared.datetime import now_iso
from ...shared.markdown import extract_links, extract_tags
from ...shared.paths import normalize_folder_path
from . import repository

# Only these are treated as note content; anything else is skipped (this
# vault only has a model for markdown-ish text notes, not binary
# attachments/blobs).
TEXT_EXTENSIONS = {".md", ".markdown", ".txt"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB — generous for hand-written notes


def split_relative_path(relative_path: str, base_folder_path: str) -> tuple[str, str]:
    """Turn an (optionally nested) relative path like 'sub/dir/My Note.md'
    into (folder_path, title), with base_folder_path prepended.

    Browsers report directory uploads via File.webkitRelativePath, which the
    frontend sends through as the multipart filename — that's the "relative
    path" this function expects, forward-slash separated.
    """
    relative_path = relative_path.replace("\\", "/").lstrip("/")
    dir_part, _, filename = relative_path.rpartition("/")
    name, ext = os.path.splitext(filename)
    title = name if ext.lower() in TEXT_EXTENSIONS else filename
    folder_path = normalize_folder_path("/".join(p for p in [base_folder_path, dir_part] if p))
    return folder_path, title.strip()


async def unique_title(owner_id: str, desired: str) -> str:
    """Titles are unique per-user across the whole vault (see the unique
    index on notes), so batch-imported files that collide with an existing
    note (or each other) get an incrementing ' (n)' suffix instead of
    failing the whole upload."""
    candidate = desired
    n = 1
    while await find_by_title(owner_id, candidate):
        n += 1
        candidate = f"{desired} ({n})"
    return candidate


async def ensure_folder_chain(owner_id: str, path: str, seen: set[str]) -> None:
    """Explicitly create every ancestor folder of `path` that doesn't exist
    yet, so an uploaded directory tree shows up in the sidebar even for
    folders that end up with no notes directly inside them."""
    if not path:
        return
    parts = path.split("/")
    for i in range(1, len(parts) + 1):
        ancestor = "/".join(parts[:i])
        if ancestor in seen:
            continue
        seen.add(ancestor)
        existing = await find_by_path(owner_id, ancestor)
        if not existing:
            await repository.insert_bare_folder(owner_id, ancestor)


async def upload_files(owner_id: str, files: list, base_folder_path: str) -> dict:
    """Batch-import one or more files as notes.

    Accepts both a handful of loose files and an entire uploaded directory
    tree in one request — each UploadFile's `filename` is treated as a path
    relative to `base_folder_path` (which itself defaults to the vault
    root), so nested folders are recreated automatically.
    """
    base_folder_path = normalize_folder_path(base_folder_path)

    created = []
    skipped = []
    folders_touched: set[str] = set()

    for upload in files:
        relative_path = upload.filename or "untitled"

        raw = await upload.read()
        if len(raw) > MAX_FILE_SIZE:
            skipped.append({"path": relative_path, "reason": "File too large (max 5MB)"})
            continue

        ext = os.path.splitext(relative_path)[1].lower()
        if ext and ext not in TEXT_EXTENSIONS:
            skipped.append({"path": relative_path, "reason": f"Unsupported file type '{ext}'"})
            continue

        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError:
            skipped.append({"path": relative_path, "reason": "Not a text file"})
            continue

        folder_path, title = split_relative_path(relative_path, base_folder_path)
        if not title:
            skipped.append({"path": relative_path, "reason": "Could not determine a note title"})
            continue

        await ensure_folder_chain(owner_id, folder_path, folders_touched)
        final_title = await unique_title(owner_id, title)

        ts = now_iso()
        doc = {
            "owner_id": owner_id,
            "title": final_title,
            "content": content,
            "folder_path": folder_path,
            "tags": extract_tags(content),
            "links": extract_links(content),
            "created_at": ts,
            "updated_at": ts,
        }
        note_id = await insert_note(doc)
        created.append(
            {
                "id": str(note_id),
                "path": relative_path,
                "title": final_title,
                "folder_path": folder_path,
                "renamed": final_title != title,
            }
        )

    return {
        "created": created,
        "skipped": skipped,
        "folders_created": sorted(folders_touched),
    }
