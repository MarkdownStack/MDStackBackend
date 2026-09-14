"""Deprecated import path — moved to app/db/{mongo,collections,indexes}.py
as part of the backend restructure (see PLAN.md). Kept as a thin re-export
so every not-yet-migrated router (see PLAN.md's Phase 3 module list) keeps
working unchanged; delete once nothing imports this."""

from .db.collections import (  # noqa: F401
    comments_collection,
    folders_collection,
    notes_collection,
    request_stats_collection,
    users_collection,
)
from .db.indexes import ensure_indexes  # noqa: F401
from .db.mongo import client, db  # noqa: F401
