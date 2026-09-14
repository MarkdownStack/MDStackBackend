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


# ExportRequest moved to app/modules/export/schemas.py as part of the
# backend restructure (see PLAN.md) — nothing outside modules/export
# imported it directly, so no re-export shim is needed here.


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


# GraphNode/GraphEdge/GraphOut above are dead code (the old graph-view
# backend endpoint, disconnected — see backend/SKILL.md's "Known open
# issues" and _removed/graph.py). Left alone here; deleting them is
# Phase 4 teardown, not part of this module's migration.

# DailyRequestCount/AdminStatsOut moved to app/modules/admin/schemas.py as
# part of the backend restructure (see PLAN.md) — nothing outside
# modules/admin imported them directly, so no re-export shim is needed
# here.
