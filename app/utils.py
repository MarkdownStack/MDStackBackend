"""Deprecated import path for the pure helpers this module used to hold —
extract_links/extract_tags/excerpt moved to app/shared/markdown.py,
normalize_folder_path/folder_scope_pattern to app/shared/paths.py (see
PLAN.md). Re-exported below so every not-yet-migrated router's
`from ..utils import ...` keeps working unchanged.

The DB-touching helpers below (derive_author_name, authors_by_owner_id,
comment_counts) are deliberately NOT moved to shared/ — they belong to
modules/users and modules/comments respectively, which don't exist until
Phase 3 migrates those routers. They stay here, working exactly as before,
until then.
"""

from bson import ObjectId
from bson.errors import InvalidId

from .db.collections import comments_collection, users_collection
from .shared.markdown import excerpt, extract_links, extract_tags  # noqa: F401
from .shared.paths import folder_scope_pattern, normalize_folder_path  # noqa: F401

# ---------------------------------------------------------------------------
# Shared by any route that renders a published-note listing — both the
# public/anonymous explore feed (routers/public.py) and the authenticated
# "my published notes" listing (routers/notes.py) need the exact same
# author-name and comment-count resolution, so it lives here once rather
# than being duplicated (and inevitably drifting) between the two routers.
# ---------------------------------------------------------------------------


def derive_author_name(email: str) -> str:
    """Fallback byline for accounts that predate the `username` field —
    derived from the part of the email before '@',
    'priya.sharma@x.com' -> 'Priya Sharma'. Once every account has a
    username (see models.UserCreate), this only ever fires for old rows."""
    local = (email or "").split("@")[0]
    cleaned = local.replace(".", " ").replace("_", " ").replace("-", " ").strip()
    return cleaned.title() if cleaned else "Someone"


async def authors_by_owner_id(owner_ids) -> dict:
    """Batch-resolve owner_id -> display author name in a single query,
    instead of one users_collection round trip per note in a list. Prefers
    the account's real username; falls back to derive_author_name for
    accounts created before that field existed."""
    oid_to_owner_id = {}
    for owner_id in owner_ids:
        try:
            oid_to_owner_id[ObjectId(owner_id)] = owner_id
        except InvalidId:
            continue
    if not oid_to_owner_id:
        return {}

    result = {}
    cursor = users_collection.find(
        {"_id": {"$in": list(oid_to_owner_id.keys())}}, {"email": 1, "username": 1}
    )
    async for doc in cursor:
        owner_id = oid_to_owner_id.get(doc["_id"])
        if owner_id:
            result[owner_id] = doc.get("username") or derive_author_name(doc.get("email", ""))
    return result


async def comment_counts(note_ids: list) -> dict:
    if not note_ids:
        return {}
    pipeline = [
        {"$match": {"note_id": {"$in": note_ids}}},
        {"$group": {"_id": "$note_id", "count": {"$sum": 1}}},
    ]
    return {doc["_id"]: doc["count"] async for doc in comments_collection.aggregate(pipeline)}
