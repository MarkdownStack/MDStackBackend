"""HTTP binding for /api/export — moved from app/routers/export.py."""

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from ...shared.dependencies import get_current_user
from . import service
from .schemas import ExportRequest

router = APIRouter(prefix="/api/export", tags=["export"])


@router.post("")
async def export_notes(payload: ExportRequest, current_user: dict = Depends(get_current_user)):
    owner_id = str(current_user["_id"])
    buffer, filename = await service.export_notes(owner_id, payload.folder_paths, payload.all)
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
