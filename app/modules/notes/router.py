"""HTTP binding for /api/notes — moved from app/routers/notes.py. All
business logic lives in service.py now; this file only translates
requests to service calls and back, so route paths, status codes, and
response_models are exactly what they were before."""

from typing import List

from fastapi import APIRouter, Depends

from ...modules.public.schemas import PublicNoteSummary
from ...shared.dependencies import get_current_user
from . import service
from .schemas import NoteCreate, NoteOut, NoteSummary, NoteUpdate

router = APIRouter(prefix="/api/notes", tags=["notes"])


@router.get("", response_model=List[NoteSummary])
async def list_notes(folder_path: str | None = None, current_user: dict = Depends(get_current_user)):
    owner_id = str(current_user["_id"])
    return await service.list_notes(owner_id, folder_path)


@router.get("/published/mine", response_model=List[PublicNoteSummary])
async def list_my_published_notes(current_user: dict = Depends(get_current_user)):
    owner_id = str(current_user["_id"])
    return await service.list_my_published_notes(owner_id)


@router.get("/{note_id}", response_model=NoteOut)
async def get_note(note_id: str, current_user: dict = Depends(get_current_user)):
    owner_id = str(current_user["_id"])
    return await service.get_note(owner_id, note_id)


@router.post("", response_model=NoteOut, status_code=201)
async def create_note(payload: NoteCreate, current_user: dict = Depends(get_current_user)):
    owner_id = str(current_user["_id"])
    return await service.create_note(owner_id, payload)


@router.put("/{note_id}", response_model=NoteOut)
async def update_note(note_id: str, payload: NoteUpdate, current_user: dict = Depends(get_current_user)):
    owner_id = str(current_user["_id"])
    return await service.update_note(owner_id, note_id, payload)


@router.delete("/{note_id}", status_code=204)
async def delete_note(note_id: str, current_user: dict = Depends(get_current_user)):
    owner_id = str(current_user["_id"])
    await service.delete_note(owner_id, note_id)
    return None
