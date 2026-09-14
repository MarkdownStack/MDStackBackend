"""Request/response models for private notes CRUD — moved from
app/models.py.

PublicNoteSummary (used by list_my_published_notes below, and by the
anonymous Explore feed) is deliberately NOT moved here — it's shared with
modules/public, which doesn't exist until a later Phase 3 step, so it
stays in app/models.py until that migration."""

from typing import List, Optional

from pydantic import BaseModel


class NoteCreate(BaseModel):
    title: str
    content: str = ""
    folder_path: str = ""  # "" = root, otherwise e.g. "projects/alpha"


class NoteUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    folder_path: Optional[str] = None
    is_public: Optional[bool] = None


class NoteOut(BaseModel):
    id: str
    title: str
    content: str
    folder_path: str
    tags: List[str] = []
    links: List[str] = []  # titles this note links to
    backlinks: List[dict] = []  # [{id, title}] notes that link to this one
    is_public: bool = False
    upvotes: int = 0
    downvotes: int = 0
    created_at: str
    updated_at: str


class NoteSummary(BaseModel):
    id: str
    title: str
    folder_path: str
    tags: List[str] = []
    is_public: bool = False
    upvotes: int = 0
    downvotes: int = 0
    created_at: str
    updated_at: str
