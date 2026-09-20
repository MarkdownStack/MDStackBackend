"""HTTP binding for /api/admin."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.postgres import get_db
from ...shared.dependencies import get_current_admin
from . import service
from .schemas import AdminStatsOut

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/stats", response_model=AdminStatsOut)
async def get_stats(admin: dict = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    return await service.get_stats(db)
