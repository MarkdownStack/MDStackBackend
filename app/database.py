import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

MONGO_URL = os.getenv("MONGO_URL", "mongodb+srv://parimal-vault:nrp1a2hkQtDNWh90@cluster0.ck6c7k4.mongodb.net/?appName=Cluster0")
DB_NAME = os.getenv("DB_NAME", "vault")

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

users_collection = db["users"]
notes_collection = db["notes"]
folders_collection = db["folders"]


async def ensure_indexes():
    await users_collection.create_index("email", unique=True)

    # Full text search across title + content
    await notes_collection.create_index([("title", "text"), ("content", "text")])
    await notes_collection.create_index("owner_id")
    await notes_collection.create_index([("owner_id", 1), ("title", 1)], unique=True)
    await notes_collection.create_index([("owner_id", 1), ("folder_path", 1)])
    await notes_collection.create_index([("owner_id", 1), ("tags", 1)])
    await notes_collection.create_index([("owner_id", 1), ("links", 1)])

    await folders_collection.create_index([("owner_id", 1), ("path", 1)], unique=True)
