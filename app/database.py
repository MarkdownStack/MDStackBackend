import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

MONGO_URL = os.getenv("MONGO_URL", "http:localhost:27017/")
DB_NAME = os.getenv("DB_NAME", "test_db")

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

users_collection = db["users"]
notes_collection = db["notes"]
folders_collection = db["folders"]
comments_collection = db["comments"]


async def ensure_indexes():
    await users_collection.create_index("email", unique=True)
    # Sparse: most users have no verification_token once verified (it's
    # $unset on success — see routers/auth.py), so this only indexes the
    # subset still pending, which is also the only subset ever looked up by it.
    await users_collection.create_index("verification_token", unique=True, sparse=True)
    # Same reasoning, for the separate forgot-password token (see
    # routers/auth.py's forgot_password/reset_password).
    await users_collection.create_index("password_reset_token", unique=True, sparse=True)

    # Full text search across title + content
    await notes_collection.create_index([("title", "text"), ("content", "text")])
    await notes_collection.create_index("owner_id")
    await notes_collection.create_index([("owner_id", 1), ("title", 1)], unique=True)
    await notes_collection.create_index([("owner_id", 1), ("folder_path", 1)])
    await notes_collection.create_index([("owner_id", 1), ("tags", 1)])
    await notes_collection.create_index([("owner_id", 1), ("links", 1)])
    # Powers the public "explore" feed's is_public filter + upvotes-desc sort.
    await notes_collection.create_index([("is_public", 1), ("upvotes", -1)])

    await folders_collection.create_index([("owner_id", 1), ("path", 1)], unique=True)
    # Powers list_my_published_folders' owner_id + is_public filter, mirroring
    # the equivalent index on notes above.
    await folders_collection.create_index([("owner_id", 1), ("is_public", 1)])

    # Powers both the per-note comment list (chronological) and any
    # future "top comments" sort by upvotes.
    await comments_collection.create_index([("note_id", 1), ("created_at", 1)])
    await comments_collection.create_index([("note_id", 1), ("upvotes", -1)])
