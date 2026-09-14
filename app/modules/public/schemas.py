"""Response models for /api/public — moved from app/models.py.

Deliberately separate from modules/notes.NoteOut/NoteSummary and
modules/folders.FolderOut: these are served with no auth check at all, so
they must never carry folder_path (except where explicitly noted for the
folder-scoped routes), links, backlinks, owner_id, or any other detail
that describes the private vault's internal structure rather than the
published note/folder itself.
"""

from typing import List

from pydantic import BaseModel, Field

# ---- Public (unauthenticated) note access -----------------------------


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
# service.py's get_public_folder/get_public_folder_note. A note showing up
# here depends only on living inside a published folder's subtree, never
# on the note's own `is_public` flag, so these are kept entirely separate
# from modules/notes' NoteSummary/NoteOut (no folder_path-outside-the-
# published-subtree, owner_id, or other private-vault detail leaks through).


class PublicFolderNoteSummary(BaseModel):
    id: str
    title: str
    folder_path: str  # relative to nothing in particular — the note's full
    # folder_path, used client-side only to group notes under their
    # subfolder in the reader's sidebar
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
# There's no account/IP tracking behind this (see service.py), so the
# client is trusted to report its own previous state honestly — the server
# just applies the delta between `previous` and `next`, clamped at 0.
class VoteUpdate(BaseModel):
    previous: int = Field(default=0, ge=-1, le=1)
    next: int = Field(default=0, ge=-1, le=1)
