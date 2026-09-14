from typing import List, Optional

from pydantic import BaseModel, Field

# Moved to app/modules/users/schemas.py as part of the backend restructure
# (see PLAN.md) — re-exported here so anything not yet repointed at the
# new module keeps working unchanged.
from .modules.users.schemas import (  # noqa: F401
    USERNAME_PATTERN,
    ForgotPasswordRequest,
    MessageOut,
    ResendVerificationRequest,
    ResetPasswordRequest,
    Token,
    UserCreate,
    UserLogin,
    UserOut,
)

# Moved to app/shared/datetime.py as part of the backend restructure (see
# PLAN.md) — now_iso isn't a schema, so it doesn't belong in this file.
# Re-exported here so every not-yet-migrated router's
# `from ..models import ... now_iso` keeps working unchanged.
from .shared.datetime import now_iso  # noqa: F401


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
    id: str | None = None
    path: str
    is_public: bool = False
    created_at: str
    updated_at: str


# Folder-level publish: the same idea as a note's own `is_public` toggle,
# one level up — makes an entire folder (and everything nested under it)
# reachable at a no-login-required URL, independent of whether any note
# inside it is individually published. See routers/folders.py.
class FolderPublishUpdate(BaseModel):
    is_public: bool


# ---- Export (vault -> downloadable .zip) -------------------------------

class ExportRequest(BaseModel):
    # Paths of the folders to include (each one pulls in that folder, every
    # note inside it, and every subfolder underneath it — same "anchored
    # prefix" scoping the recursive folder-delete uses). Ignored entirely
    # when `all` is true. An empty list with `all=False` is a 400, not "export
    # nothing" — the frontend's "All" checkbox is the explicit way to mean
    # the whole vault, so a plain empty selection is treated as a mistake.
    folder_paths: List[str] = []
    all: bool = False


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


# ---- Public (unauthenticated) folder access ----------------------------
# The folder-level counterpart to PublicNoteSummary/PublicNoteOut above.
# Reachable at /p/folder/:id with no login, same as a published note — see
# routers/public.py's get_public_folder/get_public_folder_note. A note
# showing up here depends only on living inside a published folder's
# subtree, never on the note's own `is_public` flag, so these are kept
# entirely separate from NoteSummary/NoteOut (no folder_path-outside-the-
# published-subtree, owner_id, or other private-vault detail leaks through).

class PublicFolderNoteSummary(BaseModel):
    id: str
    title: str
    folder_path: str  # relative to nothing in particular — the note's full
                       # folder_path, used client-side only to group notes
                       # under their subfolder in the reader's sidebar
    excerpt: str = ""
    tags: List[str] = []
    updated_at: str


class PublicFolderOut(BaseModel):
    id: str
    name: str  # last path segment — e.g. "alpha" for a folder at "projects/alpha"
    path: str
    author: str = "Someone"
    notes: List[PublicFolderNoteSummary] = []
    updated_at: str


# The card-grid counterpart to PublicFolderOut above — powers the Explore
# feed and the logged-out front page's "published folders" listing, the
# same relationship PublicNoteSummary has to PublicNoteOut. No note list
# here (that's what clicking through to PublicFolderOut is for) — just
# enough to render a card: how many notes it holds, who published it, and
# when it last changed.
class PublicFolderSummary(BaseModel):
    id: str
    name: str
    path: str
    author: str = "Someone"
    note_count: int = 0
    updated_at: str


class PublicFolderNoteOut(BaseModel):
    id: str
    title: str
    content: str
    folder_path: str
    tags: List[str] = []
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


# ---- Admin -------------------------------------------------------------

class DailyRequestCount(BaseModel):
    date: str
    count: int


class AdminStatsOut(BaseModel):
    total_requests: int
    requests_today: int
    requests_last_7_days: List[DailyRequestCount]
    total_users: int
    total_notes: int
    total_published_notes: int
