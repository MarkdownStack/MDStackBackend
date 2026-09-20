"""HTTP binding for /api/tags."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.postgres import get_db
from ...shared.dependencies import get_current_user
from . import service

router = APIRouter(prefix="/api/tags", tags=["tags"])


@router.get("")
async def list_tags(current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await service.list_tags(db, current_user["_id"])


@router.get("/{tag}")
async def notes_with_tag(
    tag: str, current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    return await service.notes_with_tag(db, current_user["_id"], tag)
