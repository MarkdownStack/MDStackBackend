"""All Motor calls for the users collection — moved from
app/routers/auth.py (queries) and app/database.py (collection handle)."""

from bson import ObjectId
from bson.errors import InvalidId

from ...db.collections import users_collection
from ...shared.datetime import now_iso


async def find_by_identifier(identifier: str) -> dict | None:
    """Look a user up by email OR username — both are stored lowercased
    (see insert_user below), so lowercasing the incoming identifier once
    here matches either field with a single query. Used by login and by
    the resend-verification/forgot-password recovery flows, since someone
    who signed up with a username may not remember (or want to type) their
    email for those either."""
    identifier = identifier.strip().lower()
    if not identifier:
        return None
    return await users_collection.find_one({"$or": [{"email": identifier}, {"username": identifier}]})


async def find_by_email(email: str) -> dict | None:
    return await users_collection.find_one({"email": email})


async def find_by_username(username: str) -> dict | None:
    return await users_collection.find_one({"username": username})


async def find_by_id(user_id: ObjectId) -> dict | None:
    return await users_collection.find_one({"_id": user_id})


async def find_by_verification_token(token: str) -> dict | None:
    return await users_collection.find_one({"verification_token": token})


async def find_by_reset_token(token: str) -> dict | None:
    return await users_collection.find_one({"password_reset_token": token})


async def insert_user(doc: dict) -> ObjectId:
    result = await users_collection.insert_one(doc)
    return result.inserted_id


async def mark_verified(user_id: ObjectId) -> None:
    await users_collection.update_one(
        {"_id": user_id},
        {
            "$set": {"is_verified": True, "updated_at": now_iso()},
            "$unset": {"verification_token": "", "verification_token_expires": ""},
        },
    )


async def set_verification_token(user_id: ObjectId, token: str, expires_at: str) -> None:
    await users_collection.update_one(
        {"_id": user_id},
        {"$set": {"verification_token": token, "verification_token_expires": expires_at, "updated_at": now_iso()}},
    )


async def set_password_reset_token(user_id: ObjectId, token: str, expires_at: str) -> None:
    await users_collection.update_one(
        {"_id": user_id},
        {"$set": {"password_reset_token": token, "password_reset_token_expires": expires_at, "updated_at": now_iso()}},
    )


async def update_password(user_id: ObjectId, password_hash: str) -> None:
    await users_collection.update_one(
        {"_id": user_id},
        {
            "$set": {"password_hash": password_hash, "updated_at": now_iso()},
            # Both single-use — a spent (or now-superseded) reset token
            # must never work again, same as verification_token on success.
            "$unset": {"password_reset_token": "", "password_reset_token_expires": ""},
        },
    )


# ---------------------------------------------------------------------------
# Author-name resolution — moved from app/utils.py now that this module
# exists. Used by every route that renders a published-note listing (the
# public/anonymous explore feed, "my published notes", published folders)
# so they all resolve author names identically rather than each
# reimplementing (and risking drifting from) their own version.
# ---------------------------------------------------------------------------


def derive_author_name(email: str) -> str:
    """Fallback byline for accounts that predate the `username` field —
    derived from the part of the email before '@',
    'priya.sharma@x.com' -> 'Priya Sharma'. Once every account has a
    username (see schemas.UserCreate), this only ever fires for old rows."""
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
