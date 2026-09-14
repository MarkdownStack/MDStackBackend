"""Response models for /api/admin — moved from app/models.py."""

from typing import List

from pydantic import BaseModel


class DailyRequestCount(BaseModel):
    date: str
    count: int


class AdminStatsOut(BaseModel):
    total_requests: int
    requests_today: int
    requests_last_7_days: List[DailyRequestCount]
    total_users: int
    total_notes: int
    total_published_notes: int
