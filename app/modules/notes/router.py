"""HTTP binding for /api/notes. All business logic lives in service.py;
this file only translates requests to service calls and back, so route
paths, status codes, and response_models are exactly what they were
before this migration."""

from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.postgres import get_db
from ...modules.public.schemas import PublicNoteSummary
from ...shared.dependencies import get_current_user
from . import service
from .schemas import NoteCreate, NoteOut, NoteSummary, NoteUpdate

router = APIRouter(prefix="/api/notes", tags=["notes"])


@router.get("", response_model=List[NoteSummary])
async def list_notes(
    folder_path: str | None = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await service.list_notes(db, current_user["_id"], folder_path)


@router.get("/published/mine", response_model=List[PublicNoteSummary])
async def list_my_published_notes(current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await service.list_my_published_notes(db, current_user["_id"])


@router.get("/{note_id}", response_model=NoteOut)
async def get_note(note_id: str, current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await service.get_note(db, current_user["_id"], note_id)


@router.post("", response_model=NoteOut, status_code=201)
async def create_note(
    payload: NoteCreate, current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    return await service.create_note(db, current_user["_id"], payload)


@router.put("/{note_id}", response_model=NoteOut)
async def update_note(
    note_id: str,
    payload: NoteUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await service.update_note(db, current_user["_id"], note_id, payload)


@router.delete("/{note_id}", status_code=204)
async def delete_note(
    note_id: str, current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    await service.delete_note(db, current_user["_id"], note_id)
    return None
