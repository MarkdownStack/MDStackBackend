"""HTTP binding for the /api/public/notes/{note_id}/comments* routes."""

from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.postgres import get_db
from ...shared.dependencies import get_current_user
from . import service
from .schemas import CommentCreate, CommentOut

router = APIRouter(prefix="/api/public", tags=["public"])


@router.get("/notes/{note_id}/comments", response_model=List[CommentOut])
async def list_comments(note_id: str, db: AsyncSession = Depends(get_db)):
    return await service.list_comments(db, note_id)


@router.post("/notes/{note_id}/comments", response_model=CommentOut, status_code=201)
async def create_comment(
    note_id: str,
    payload: CommentCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await service.create_comment(db, note_id, current_user["_id"], payload)


@router.post("/notes/{note_id}/comments/{comment_id}/upvote", response_model=CommentOut)
async def upvote_comment(note_id: str, comment_id: str, db: AsyncSession = Depends(get_db)):
    return await service.upvote_comment(db, note_id, comment_id)
