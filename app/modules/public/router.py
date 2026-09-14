"""HTTP binding for /api/public's note/folder routes — moved from
app/routers/public.py. Comment routes live in modules/comments/router.py
instead (same /api/public prefix — comments have their own collection, so
their own module — see PLAN.md).

Reading is public everywhere in this file — no auth dependency on any GET,
and a note's own is_public flag (checked explicitly in service.py) is the
only thing standing between it and the whole internet."""

from typing import List

from fastapi import APIRouter, Depends

from ...shared.dependencies import get_current_user_optional
from . import service
from .schemas import (
    PublicFolderNoteOut,
    PublicFolderOut,
    PublicFolderSummary,
    PublicNoteOut,
    PublicNoteSummary,
    VoteUpdate,
)

router = APIRouter(prefix="/api/public", tags=["public"])


@router.get("/notes", response_model=List[PublicNoteSummary])
async def list_public_notes(limit: int = 100, current_user: dict | None = Depends(get_current_user_optional)):
    current_user_id = str(current_user["_id"]) if current_user else None
    return await service.list_public_notes(limit, current_user_id)


@router.get("/notes/{note_id}", response_model=PublicNoteOut)
async def get_public_note(note_id: str):
    return await service.get_public_note(note_id)


@router.post("/notes/{note_id}/vote", response_model=PublicNoteOut)
async def vote_public_note(note_id: str, payload: VoteUpdate):
    return await service.vote_public_note(note_id, payload)


@router.get("/folders", response_model=List[PublicFolderSummary])
async def list_public_folders(limit: int = 100, current_user: dict | None = Depends(get_current_user_optional)):
    current_user_id = str(current_user["_id"]) if current_user else None
    return await service.list_public_folders(limit, current_user_id)


@router.get("/folders/{folder_id}", response_model=PublicFolderOut)
async def get_public_folder(folder_id: str):
    return await service.get_public_folder(folder_id)


@router.get("/folders/{folder_id}/notes/{note_id}", response_model=PublicFolderNoteOut)
async def get_public_folder_note(folder_id: str, note_id: str):
    return await service.get_public_folder_note(folder_id, note_id)
