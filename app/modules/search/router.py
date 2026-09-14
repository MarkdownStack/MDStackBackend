"""HTTP binding for /api/search — moved from app/routers/search.py."""

from fastapi import APIRouter, Depends, Query

from ...shared.dependencies import get_current_user
from . import service

router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("")
async def search_notes(q: str = Query(..., min_length=1), current_user: dict = Depends(get_current_user)):
    owner_id = str(current_user["_id"])
    return await service.search_notes(owner_id, q)
