"""HTTP binding for /api/tags — moved from app/routers/tags.py."""

from fastapi import APIRouter, Depends

from ...shared.dependencies import get_current_user
from . import service

router = APIRouter(prefix="/api/tags", tags=["tags"])


@router.get("")
async def list_tags(current_user: dict = Depends(get_current_user)):
    owner_id = str(current_user["_id"])
    return await service.list_tags(owner_id)


@router.get("/{tag}")
async def notes_with_tag(tag: str, current_user: dict = Depends(get_current_user)):
    owner_id = str(current_user["_id"])
    return await service.notes_with_tag(owner_id, tag)
