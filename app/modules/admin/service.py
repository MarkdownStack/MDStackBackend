"""Business logic for /api/admin/stats. Behavior unchanged from before
this migration."""

from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from . import repository
from .schemas import AdminStatsOut, DailyRequestCount


async def get_stats(db: AsyncSession) -> AdminStatsOut:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Sum of every daily bucket is the all-time total. One row per calendar
    # day since launch is a tiny table at any real-world scale for this
    # app, so summing on read beats maintaining a separate "all-time"
    # counter (and the extra write contention that'd add to every request).
    total_requests = await repository.sum_all_request_counts(db)

    requests_today = await repository.get_count_for_date(db, today)

    last_7_dates = [(datetime.now(timezone.utc) - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(6, -1, -1)]
    counts_by_date = await repository.get_counts_for_dates(db, last_7_dates)
    requests_last_7_days = [DailyRequestCount(date=d, count=counts_by_date.get(d, 0)) for d in last_7_dates]

    total_users = await repository.count_users(db)
    total_notes = await repository.count_notes(db)
    total_published_notes = await repository.count_published_notes(db)

    return AdminStatsOut(
        total_requests=total_requests,
        requests_today=requests_today,
        requests_last_7_days=requests_last_7_days,
        total_users=total_users,
        total_notes=total_notes,
        total_published_notes=total_published_notes,
    )
