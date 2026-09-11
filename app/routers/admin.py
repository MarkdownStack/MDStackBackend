from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends

from ..database import notes_collection, request_stats_collection, users_collection
from ..dependencies import get_current_admin
from ..models import AdminStatsOut, DailyRequestCount

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/stats", response_model=AdminStatsOut)
async def get_stats(admin: dict = Depends(get_current_admin)):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Sum of every daily bucket is the all-time total. One doc per calendar
    # day since launch is a tiny collection at any real-world scale for
    # this app, so summing on read beats maintaining a separate "all-time"
    # counter (and the extra write contention that'd add to every request).
    total_requests = 0
    async for doc in request_stats_collection.find({}, {"count": 1}):
        total_requests += doc.get("count", 0)

    today_doc = await request_stats_collection.find_one({"_id": today}, {"count": 1})
    requests_today = today_doc.get("count", 0) if today_doc else 0

    last_7_dates = [
        (datetime.now(timezone.utc) - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(6, -1, -1)
    ]
    counts_by_date = {}
    async for doc in request_stats_collection.find({"_id": {"$in": last_7_dates}}, {"count": 1}):
        counts_by_date[doc["_id"]] = doc.get("count", 0)
    requests_last_7_days = [
        DailyRequestCount(date=d, count=counts_by_date.get(d, 0)) for d in last_7_dates
    ]

    total_users = await users_collection.count_documents({})
    total_notes = await notes_collection.count_documents({})
    total_published_notes = await notes_collection.count_documents({"is_public": True})

    return AdminStatsOut(
        total_requests=total_requests,
        requests_today=requests_today,
        requests_last_7_days=requests_last_7_days,
        total_users=total_users,
        total_notes=total_notes,
        total_published_notes=total_published_notes,
    )
