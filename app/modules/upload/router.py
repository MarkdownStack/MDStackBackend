"""HTTP binding for /api/upload."""

from typing import List

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.postgres import get_db
from ...shared.dependencies import get_current_user
from . import service

router = APIRouter(prefix="/api/upload", tags=["upload"])


@router.post("", status_code=201)
async def upload_files(
    files: List[UploadFile] = File(...),
    base_folder_path: str = Form(""),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Batch-import one or more files as notes.

    Accepts both a handful of loose files and an entire uploaded directory
    tree in one request — each UploadFile's `filename` is treated as a path
    relative to `base_folder_path` (which itself defaults to the vault
    root), so nested folders are recreated automatically.
    """
    return await service.upload_files(db, current_user["_id"], files, base_folder_path)
