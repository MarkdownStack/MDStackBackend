"""Business logic for /api/admin/stats — moved from app/routers/admin.py.
Behavior unchanged."""

from datetime import datetime, timedelta, timezone

from . import repository
from .schemas import AdminStatsOut, DailyRequestCount


async def get_stats() -> AdminStatsOut:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Sum of every daily bucket is the all-time total. One doc per calendar
    # day since launch is a tiny collection at any real-world scale for
    # this app, so summing on read beats maintaining a separate "all-time"
    # counter (and the extra write contention that'd add to every request).
    total_requests = await repository.sum_all_request_counts()

    requests_today = await repository.get_count_for_date(today)

    last_7_dates = [(datetime.now(timezone.utc) - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(6, -1, -1)]
    counts_by_date = await repository.get_counts_for_dates(last_7_dates)
    requests_last_7_days = [DailyRequestCount(date=d, count=counts_by_date.get(d, 0)) for d in last_7_dates]

    total_users = await repository.count_users()
    total_notes = await repository.count_notes()
    total_published_notes = await repository.count_published_notes()

    return AdminStatsOut(
        total_requests=total_requests,
        requests_today=requests_today,
        requests_last_7_days=requests_last_7_days,
        total_users=total_users,
        total_notes=total_notes,
        total_published_notes=total_published_notes,
    )
