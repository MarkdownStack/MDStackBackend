from typing import List

from pydantic import BaseModel

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

# NoteCreate/NoteUpdate/NoteOut/NoteSummary moved to
# app/modules/notes/schemas.py as part of the backend restructure (see
# PLAN.md) — nothing outside modules/notes imported them directly, so no
# re-export shim is needed here.


# FolderCreate/FolderOut/FolderPublishUpdate moved to
# app/modules/folders/schemas.py as part of the backend restructure (see
# PLAN.md) — nothing outside modules/folders imported them directly, so no
# re-export shim is needed here.

# PublicNoteSummary/PublicNoteOut/PublicFolderNoteSummary/PublicFolderOut/
# PublicFolderSummary/PublicFolderNoteOut/VoteUpdate moved to
# app/modules/public/schemas.py, and CommentCreate/CommentOut to
# app/modules/comments/schemas.py, as part of the backend restructure (see
# PLAN.md) — grep confirmed nothing outside modules/notes and
# modules/folders (both already updated to import from the new locations)
# imported these directly, so no re-export shim is needed here.


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
