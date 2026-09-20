"""HTTP binding for /api/folders. All business logic lives in service.py;
this file only translates requests to service calls and back, so route
paths, status codes, and response_models are exactly what they were
before this migration."""

from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.postgres import get_db
from ...modules.public.schemas import PublicFolderSummary
from ...shared.dependencies import get_current_user
from . import service
from .schemas import FolderCreate, FolderOut, FolderPublishUpdate

router = APIRouter(prefix="/api/folders", tags=["folders"])


@router.get("")
async def list_folders(current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await service.list_folders(db, current_user["_id"])


@router.post("", status_code=201)
async def create_folder(
    payload: FolderCreate, current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    return await service.create_folder(db, current_user["_id"], payload.path)


@router.delete("/{path:path}", status_code=200)
async def delete_folder(
    path: str, current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    return await service.delete_folder(db, current_user["_id"], path)


@router.get("/published/mine", response_model=List[PublicFolderSummary])
async def list_my_published_folders(
    current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    return await service.list_my_published_folders(db, current_user["_id"])


@router.put("/{path:path}/publish", response_model=FolderOut)
async def set_folder_publish(
    path: str,
    payload: FolderPublishUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await service.set_folder_publish(db, current_user["_id"], path, payload)
