from pydantic import BaseModel, EmailStr, Field
from typing import List, Optional
from datetime import datetime, timezone


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---- Auth / Users ----------------------------------------------------

# Letters, numbers, and underscores only — no dots/spaces (keeps it
# unambiguous as a login identifier alongside an email address, and safe to
# show as a byline with no further sanitizing).
USERNAME_PATTERN = r"^[a-zA-Z0-9_]{3,24}$"


class UserCreate(BaseModel):
    username: str = Field(pattern=USERNAME_PATTERN)
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: str
    username: str = ""
    email: str
    is_verified: bool = False
    created_at: str
    updated_at: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ---- Email verification ------------------------------------------------
# Registering creates the account immediately but leaves is_verified=False
# on the user document until the link Mailgun sends (see app/email.py) is
# clicked — /api/auth/login refuses unverified accounts (403, not 401,
# since the credentials themselves were correct) so a signup that never
# checks their inbox can't silently end up "logged in but unconfirmed".

class ResendVerificationRequest(BaseModel):
    # Email or username — login now accepts either (see routers/auth.py's
    # login), so "resend my verification email" has to accept whichever one
    # someone actually remembers signing in with.
    identifier: str


class MessageOut(BaseModel):
    message: str


# ---- Forgot / reset password -------------------------------------------
# Same shape as email verification (a random token + expiry stored on the
# user document, emailed as a link) — see routers/auth.py's
# forgot_password/reset_password and app/email.py's
# send_password_reset_email. Kept as its own token field
# (password_reset_token) rather than reusing verification_token so a
# pending signup-verification link and a pending password-reset link can
# never collide or invalidate each other on the same account.

class ForgotPasswordRequest(BaseModel):
    # Same reasoning as ResendVerificationRequest.identifier above.
    identifier: str


class ResetPasswordRequest(BaseModel):
    token: str
    password: str = Field(min_length=8, max_length=72)


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
