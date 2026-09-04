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
    updated_at: str


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
    is_public: Optional[bool] = None


class NoteOut(BaseModel):
    id: str
    title: str
    content: str
    folder_path: str
    tags: List[str] = []
    links: List[str] = []          # titles this note links to
    backlinks: List[dict] = []     # [{id, title}] notes that link to this one
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


class FolderCreate(BaseModel):
    path: str  # full path e.g. "projects/alpha"


class FolderOut(BaseModel):
    path: str
    created_at: str
    updated_at: str


# ---- Public (unauthenticated) note access -----------------------------
# Deliberately separate from NoteOut/NoteSummary: these are served with no
# auth check at all, so they must never carry folder_path, links, backlinks,
# or owner_id — anything that describes the private vault's internal
# structure rather than the published note itself.

class PublicNoteSummary(BaseModel):
    id: str
    title: str
    excerpt: str = ""
    tags: List[str] = []
    author: str = "Someone"
    upvotes: int = 0
    downvotes: int = 0
    comment_count: int = 0
    updated_at: str


class PublicNoteOut(BaseModel):
    id: str
    title: str
    content: str
    tags: List[str] = []
    author: str = "Someone"
    upvotes: int = 0
    downvotes: int = 0
    comment_count: int = 0
    updated_at: str


# A reader's vote on a note is either up (1), down (-1), or retracted (0).
# There's no account/IP tracking behind this (see routers/public.py), so the
# client is trusted to report its own previous state honestly — the server
# just applies the delta between `previous` and `next`, clamped at 0.
class VoteUpdate(BaseModel):
    previous: int = Field(default=0, ge=-1, le=1)
    next: int = Field(default=0, ge=-1, le=1)


# ---- Comments (feedback on a published note, from signed-in users only) --
# Reading a published note (and its comments) needs no account. Posting a
# comment does — see the auth dependency on create_comment in
# routers/public.py — so `author` is always resolved from the commenter's
# real account rather than a free-typed name.

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
