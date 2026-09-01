from fastapi import APIRouter, Depends, HTTPException

from ..database import folders_collection, notes_collection
from ..dependencies import get_current_user
from ..models import FolderCreate
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
    await folders_collection.insert_one({"path": path, "owner_id": owner_id})
    return {"path": path}


@router.delete("/{path:path}", status_code=204)
async def delete_folder(path: str, current_user: dict = Depends(get_current_user)):
    owner_id = str(current_user["_id"])
    path = normalize_folder_path(path)
    in_use = await notes_collection.find_one(
        {"folder_path": {"$regex": f"^{path}"}, "owner_id": owner_id}
    )
    if in_use:
        raise HTTPException(status_code=409, detail="Move or delete notes inside this folder first")
    await folders_collection.delete_one({"path": path, "owner_id": owner_id})
    return None
