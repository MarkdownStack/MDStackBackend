import re

from bson import ObjectId
from bson.errors import InvalidId

from .database import users_collection, comments_collection

# [[Note Title]] or [[Note Title|Display Text]]
WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:\|[^\]]+)?\]\]")

# #tag  (letters, numbers, dashes, underscores, forward-slash for nested tags like #project/alpha)
TAG_RE = re.compile(r"(?<!\w)#([a-zA-Z0-9_\-/]+)")


def extract_links(content: str) -> list[str]:
    """Return unique, order-preserving list of wikilink titles referenced in content."""
    seen = []
    for match in WIKILINK_RE.finditer(content):
        title = match.group(1).strip()
        if title and title not in seen:
            seen.append(title)
    return seen


def extract_tags(content: str) -> list[str]:
    """Return unique, order-preserving list of #tags referenced in content."""
    seen = []
    for match in TAG_RE.finditer(content):
        tag = match.group(1).strip()
        if tag and tag not in seen:
            seen.append(tag)
    return seen


def normalize_folder_path(path: str) -> str:
    path = (path or "").strip().strip("/")
    # collapse duplicate slashes
    parts = [p for p in path.split("/") if p]
    return "/".join(parts)


_MD_STRIP_RE = re.compile(r"[`*_#>\[\]()~-]")
_WS_RE = re.compile(r"\s+")


def excerpt(content: str, length: int = 200) -> str:
    """Plain-text preview for a public note listing — strips the most common
    markdown punctuation and collapses whitespace/newlines so a card preview
    doesn't show raw '#', '*', or '[[' characters, then truncates."""
    stripped = _WS_RE.sub(" ", _MD_STRIP_RE.sub(" ", content)).strip()
    if len(stripped) <= length:
        return stripped
    return stripped[:length].rsplit(" ", 1)[0] + "…"


# ---------------------------------------------------------------------------
# Shared by any route that renders a published-note listing — both the
# public/anonymous explore feed (routers/public.py) and the authenticated
# "my published notes" listing (routers/notes.py) need the exact same
# author-name and comment-count resolution, so it lives here once rather
# than being duplicated (and inevitably drifting) between the two routers.
# ---------------------------------------------------------------------------

def derive_author_name(email: str) -> str:
    """No display-name field on users yet, so the byline is derived from the
    part of the email before '@' — 'priya.sharma@x.com' -> 'Priya Sharma'."""
    local = (email or "").split("@")[0]
    cleaned = local.replace(".", " ").replace("_", " ").replace("-", " ").strip()
    return cleaned.title() if cleaned else "Someone"


async def authors_by_owner_id(owner_ids) -> dict:
    """Batch-resolve owner_id -> display author name in a single query,
    instead of one users_collection round trip per note in a list."""
    oid_to_owner_id = {}
    for owner_id in owner_ids:
        try:
            oid_to_owner_id[ObjectId(owner_id)] = owner_id
        except InvalidId:
            continue
    if not oid_to_owner_id:
        return {}

    result = {}
    cursor = users_collection.find({"_id": {"$in": list(oid_to_owner_id.keys())}}, {"email": 1})
    async for doc in cursor:
        owner_id = oid_to_owner_id.get(doc["_id"])
        if owner_id:
            result[owner_id] = derive_author_name(doc.get("email", ""))
    return result


async def comment_counts(note_ids: list) -> dict:
    if not note_ids:
        return {}
    pipeline = [
        {"$match": {"note_id": {"$in": note_ids}}},
        {"$group": {"_id": "$note_id", "count": {"$sum": 1}}},
    ]
    return {doc["_id"]: doc["count"] async for doc in comments_collection.aggregate(pipeline)}
