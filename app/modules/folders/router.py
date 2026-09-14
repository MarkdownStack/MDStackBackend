"""HTTP binding for /api/folders — moved from app/routers/folders.py. All
business logic lives in service.py now; this file only translates
requests to service calls and back, so route paths, status codes, and
response_models are exactly what they were before."""

from typing import List

from fastapi import APIRouter, Depends

from ...models import PublicFolderSummary
from ...shared.dependencies import get_current_user
from . import service
from .schemas import FolderCreate, FolderOut, FolderPublishUpdate

router = APIRouter(prefix="/api/folders", tags=["folders"])


@router.get("")
async def list_folders(current_user: dict = Depends(get_current_user)):
    owner_id = str(current_user["_id"])
    return await service.list_folders(owner_id)


@router.post("", status_code=201)
async def create_folder(payload: FolderCreate, current_user: dict = Depends(get_current_user)):
    owner_id = str(current_user["_id"])
    return await service.create_folder(owner_id, payload.path)


@router.delete("/{path:path}", status_code=200)
async def delete_folder(path: str, current_user: dict = Depends(get_current_user)):
    owner_id = str(current_user["_id"])
    return await service.delete_folder(owner_id, path)


@router.get("/published/mine", response_model=List[PublicFolderSummary])
async def list_my_published_folders(current_user: dict = Depends(get_current_user)):
    owner_id = str(current_user["_id"])
    return await service.list_my_published_folders(owner_id)


@router.put("/{path:path}/publish", response_model=FolderOut)
async def set_folder_publish(
    path: str, payload: FolderPublishUpdate, current_user: dict = Depends(get_current_user)
):
    owner_id = str(current_user["_id"])
    return await service.set_folder_publish(owner_id, path, payload)
