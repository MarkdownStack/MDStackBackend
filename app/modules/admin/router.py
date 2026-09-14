"""HTTP binding for /api/admin — moved from app/routers/admin.py."""

from fastapi import APIRouter, Depends

from ...shared.dependencies import get_current_admin
from . import service
from .schemas import AdminStatsOut

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/stats", response_model=AdminStatsOut)
async def get_stats(admin: dict = Depends(get_current_admin)):
    return await service.get_stats()
