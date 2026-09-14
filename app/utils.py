"""Deprecated import path for the pure helpers this module used to hold —
extract_links/extract_tags/excerpt moved to app/shared/markdown.py,
normalize_folder_path/folder_scope_pattern to app/shared/paths.py, and
derive_author_name/authors_by_owner_id to app/modules/users/repository.py
now that that module exists (see PLAN.md). Re-exported below so every
not-yet-migrated router's `from ..utils import ...` keeps working
unchanged.

comment_counts below is deliberately NOT moved yet — it belongs to
modules/comments, which doesn't exist until a later Phase 3 step. It stays
here, working exactly as before, until then.
"""

from .db.collections import comments_collection
from .modules.users.repository import authors_by_owner_id, derive_author_name  # noqa: F401
from .shared.markdown import excerpt, extract_links, extract_tags  # noqa: F401
from .shared.paths import folder_scope_pattern, normalize_folder_path  # noqa: F401


async def comment_counts(note_ids: list) -> dict:
    if not note_ids:
        return {}
    pipeline = [
        {"$match": {"note_id": {"$in": note_ids}}},
        {"$group": {"_id": "$note_id", "count": {"$sum": 1}}},
    ]
    return {doc["_id"]: doc["count"] async for doc in comments_collection.aggregate(pipeline)}
