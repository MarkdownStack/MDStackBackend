"""Request/response models for comments — moved from app/models.py."""

from pydantic import BaseModel, Field


class CommentCreate(BaseModel):
    content: str = Field(min_length=1, max_length=2000)


class CommentOut(BaseModel):
    id: str
    note_id: str
    author: str
    upvotes: int = 0
    content: str
    created_at: str
    updated_at: str
