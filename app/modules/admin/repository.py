"""Motor calls for /api/admin/stats — moved from app/routers/admin.py
(queries) and app/database.py (collection handles)."""

from ...db.collections import notes_collection, request_stats_collection, users_collection


async def sum_all_request_counts() -> int:
    total = 0
    async for doc in request_stats_collection.find({}, {"count": 1}):
        total += doc.get("count", 0)
    return total


async def get_count_for_date(date: str) -> int:
    doc = await request_stats_collection.find_one({"_id": date}, {"count": 1})
    return doc.get("count", 0) if doc else 0


async def get_counts_for_dates(dates: list[str]) -> dict[str, int]:
    counts_by_date: dict[str, int] = {}
    async for doc in request_stats_collection.find({"_id": {"$in": dates}}, {"count": 1}):
        counts_by_date[doc["_id"]] = doc.get("count", 0)
    return counts_by_date


async def count_users() -> int:
    return await users_collection.count_documents({})


async def count_notes() -> int:
    return await notes_collection.count_documents({})


async def count_published_notes() -> int:
    return await notes_collection.count_documents({"is_public": True})
