import re

from fastapi import APIRouter, Depends, HTTPException

from ..database import folders_collection, notes_collection
from ..dependencies import get_current_user
from ..models import FolderCreate, now_iso
from ..utils import normalize_folder_path

router = APIRouter(prefix="/api/folders", tags=["folders"])


@router.get("")
async def list_folders(current_user: dict = Depends(get_current_user)):
    """Return every known folder path for this user (explicitly created OR implied by a note)."""
    owner_id = str(current_user["_id"])
    explicit = {doc["path"] async for doc in folders_collection.find({"owner_id": owner_id}, {"path": 1})}
    implied = {
        doc["folder_path"]
        async for doc in notes_collection.find({"owner_id": owner_id}, {"folder_path": 1})
        if doc.get("folder_path")
    }
    all_paths = sorted(p for p in (explicit | implied) if p)
    return {"paths": all_paths}


@router.post("", status_code=201)
async def create_folder(payload: FolderCreate, current_user: dict = Depends(get_current_user)):
    owner_id = str(current_user["_id"])
    path = normalize_folder_path(payload.path)
    if not path:
        raise HTTPException(status_code=400, detail="Folder path cannot be empty")
    existing = await folders_collection.find_one({"path": path, "owner_id": owner_id})
    if existing:
        raise HTTPException(status_code=409, detail="Folder already exists")
    ts = now_iso()
    await folders_collection.insert_one({"path": path, "owner_id": owner_id, "created_at": ts, "updated_at": ts})
    return {"path": path, "created_at": ts, "updated_at": ts}


@router.delete("/{path:path}", status_code=200)
async def delete_folder(path: str, current_user: dict = Depends(get_current_user)):
    """Delete a folder and cascade: every note directly inside it, every
    note inside any of its subfolders, and the subfolders themselves all go
    with it. There's no recycle bin for this, so the frontend is expected to
    confirm with the user before calling this — see Sidebar.jsx."""
    owner_id = str(current_user["_id"])
    path = normalize_folder_path(path)
    if not path:
        raise HTTPException(status_code=400, detail="Cannot delete the vault root")

    # Anchored + escaped so this matches `path` itself and anything nested
    # under it (`path/...`) but never a sibling that merely starts with the
    # same characters — e.g. deleting "notes" must not touch "notes-archive".
    # (The old version of this check used an unescaped, unanchored prefix
    # regex, which is also what used to let an unrelated sibling wrongly
    # block a delete in the first place.)
    pattern = f"^{re.escape(path)}(/.*)?$"
    folder_scope = {"owner_id": owner_id, "path": {"$regex": pattern}}
    note_scope = {"owner_id": owner_id, "folder_path": {"$regex": pattern}}

    # Folders aren't always backed by an explicit folders_collection doc —
    # one implied purely by a note's folder_path (never separately created,
    # never touched by ensure_folder_chain) still shows up in the sidebar
    # tree, so "not found" has to mean "nothing at all lives at this path",
    # not just "no explicit folder doc".
    has_folder_doc = await folders_collection.find_one(folder_scope)
    has_notes = await notes_collection.find_one(note_scope)
    if not has_folder_doc and not has_notes:
        raise HTTPException(status_code=404, detail="Folder not found")

    notes_result = await notes_collection.delete_many(note_scope)
    folders_result = await folders_collection.delete_many(folder_scope)

    return {
        "path": path,
        "deleted_notes": notes_result.deleted_count,
        "deleted_folders": folders_result.deleted_count,
    }
