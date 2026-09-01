from pydantic import BaseModel, EmailStr, Field
from typing import List, Optional
from datetime import datetime, timezone


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---- Auth / Users ----------------------------------------------------

class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: str
    email: str
    created_at: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class NoteCreate(BaseModel):
    title: str
    content: str = ""
    folder_path: str = ""  # "" = root, otherwise e.g. "projects/alpha"


class NoteUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    folder_path: Optional[str] = None


class NoteOut(BaseModel):
    id: str
    title: str
    content: str
    folder_path: str
    tags: List[str] = []
    links: List[str] = []          # titles this note links to
    backlinks: List[dict] = []     # [{id, title}] notes that link to this one
    created_at: str
    updated_at: str


class NoteSummary(BaseModel):
    id: str
    title: str
    folder_path: str
    tags: List[str] = []
    updated_at: str


class FolderCreate(BaseModel):
    path: str  # full path e.g. "projects/alpha"


class GraphNode(BaseModel):
    id: str
    label: str
    folder_path: str


class GraphEdge(BaseModel):
    source: str
    target: str


class GraphOut(BaseModel):
    nodes: List[GraphNode]
    edges: List[GraphEdge]
