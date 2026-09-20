"""HTTP binding for /api/search."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.postgres import get_db
from ...shared.dependencies import get_current_user
from . import service

router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("")
async def search_notes(
    q: str = Query(..., min_length=1),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await service.search_notes(db, current_user["_id"], q)
