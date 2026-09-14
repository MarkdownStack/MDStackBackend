"""Mongo client lifecycle — moved from the top half of app/database.py.

The client itself is still created eagerly at import (Motor's
AsyncIOMotorClient doesn't open a real socket until first use, so this
matches today's behavior exactly — no new connect-on-startup timing to
worry about). The one real addition is close(), called from the app's
lifespan on shutdown (see app/main.py) — today's client is never closed at
all.
"""

from motor.motor_asyncio import AsyncIOMotorClient

from ..core.config import get_settings

settings = get_settings()

client: AsyncIOMotorClient = AsyncIOMotorClient(settings.mongo_url)
db = client[settings.db_name]


async def close() -> None:
    # AsyncIOMotorClient.close() is a plain sync call (it just tears down
    # the underlying connection pool) — this wrapper is async purely so the
    # lifespan shutdown handler can await it like everything else there.
    client.close()
