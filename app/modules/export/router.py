"""HTTP binding for /api/export."""

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.postgres import get_db
from ...shared.dependencies import get_current_user
from . import service
from .schemas import ExportRequest

router = APIRouter(prefix="/api/export", tags=["export"])


@router.post("")
async def export_notes(
    payload: ExportRequest, current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    buffer, filename = await service.export_notes(db, current_user["_id"], payload.folder_paths, payload.all)
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
