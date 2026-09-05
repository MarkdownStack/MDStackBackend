import io
import re
import zipfile
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from ..database import notes_collection, folders_collection
from ..dependencies import get_current_user
from ..models import ExportRequest
from ..utils import normalize_folder_path

router = APIRouter(prefix="/api/export", tags=["export"])

# Same "only these are real note content" list upload.py uses — kept in
# sync manually since a note's title has no stored extension of its own;
# .md is what round-trips cleanly back through the upload importer.
NOTE_EXTENSION = ".md"

_INVALID_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|]')


def sanitize_filename(name: str) -> str:
    """Strip characters that are illegal in a filename on Windows/macOS/Linux
    (a note title is free-form text and may contain any of them) so the zip
    extracts cleanly everywhere, not just on whatever OS the note was
    originally written on."""
    cleaned = _INVALID_FILENAME_CHARS.sub("_", name or "").strip().rstrip(".")
    return cleaned or "untitled"


def unique_filename(used: set, base: str, ext: str) -> str:
    """Same collision handling as upload.py's unique_title, mirrored here in
    the other direction: two live notes can share a title if they live in
    different folders, but only one of them lands in any given zip
    directory, so a same-named sibling needs a ' (n)' suffix instead of
    silently overwriting the first file written."""
    candidate = f"{base}{ext}"
    n = 1
    while candidate in used:
        n += 1
        candidate = f"{base} ({n}){ext}"
    used.add(candidate)
    return candidate


@router.post("")
async def export_notes(payload: ExportRequest, current_user: dict = Depends(get_current_user)):
    """Bundle the vault (or a chosen subset of its folders) into a .zip and
    stream it back for download. Folder structure is recreated exactly,
    including folders that have no notes of their own directly inside them
    (only subfolders), so importing the zip back in via /api/upload
    reconstructs the same tree.
    """
    owner_id = str(current_user["_id"])

    if payload.all:
        note_query: dict = {"owner_id": owner_id}
        folder_query: dict = {"owner_id": owner_id}
    else:
        selected = sorted({normalize_folder_path(p) for p in payload.folder_paths if normalize_folder_path(p)})
        if not selected:
            raise HTTPException(status_code=400, detail="Select at least one folder, or choose \"All\"")
        # Anchored + escaped, same scoping the recursive folder-delete uses:
        # each selected path pulls in itself, its notes, and everything
        # nested under it — never an unrelated sibling that happens to share
        # a prefix (selecting "notes" must not also grab "notes-archive").
        or_clauses = [{"$regex": f"^{re.escape(p)}(/.*)?$"} for p in selected]
        note_query = {"owner_id": owner_id, "$or": [{"folder_path": c} for c in or_clauses]}
        folder_query = {"owner_id": owner_id, "$or": [{"path": c} for c in or_clauses]}

    notes = [doc async for doc in notes_collection.find(note_query)]
    folders = [doc async for doc in folders_collection.find(folder_query)]

    if not notes and not folders:
        raise HTTPException(status_code=404, detail="Nothing to export in the selected folder(s)")

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        # Write an explicit entry for every folder and every one of its
        # ancestors, so an empty folder (no notes directly inside, only
        # sitting there as an organizational placeholder) still shows up
        # when the zip is extracted — without this, only folders that
        # happen to contain a note would survive the round trip.
        all_dir_paths = {f["path"] for f in folders} | {n["folder_path"] for n in notes if n.get("folder_path")}
        written_dirs = set()
        for path in sorted(all_dir_paths):
            parts = path.split("/")
            for i in range(1, len(parts) + 1):
                ancestor = "/".join(parts[:i])
                if ancestor not in written_dirs:
                    written_dirs.add(ancestor)
                    zf.writestr(ancestor + "/", "")

        # Track filenames already used *per directory* — a title collision
        # across different folders is fine, only same-folder collisions
        # need the " (n)" suffix.
        used_by_dir: dict = {}
        for note in notes:
            folder_path = note.get("folder_path") or ""
            used = used_by_dir.setdefault(folder_path, set())
            filename = unique_filename(used, sanitize_filename(note.get("title") or "untitled"), NOTE_EXTENSION)
            full_path = f"{folder_path}/{filename}" if folder_path else filename
            zf.writestr(full_path, note.get("content") or "")

    buffer.seek(0)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    filename = f"markdownstack-export-{stamp}.zip"
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
