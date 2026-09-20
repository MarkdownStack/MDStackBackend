"""Queries for /api/admin/stats."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.models import Note, RequestStat, User


async def sum_all_request_counts(session: AsyncSession) -> int:
    result = await session.execute(select(func.coalesce(func.sum(RequestStat.count), 0)))
    return result.scalar_one()


async def get_count_for_date(session: AsyncSession, date: str) -> int:
    result = await session.execute(select(RequestStat.count).where(RequestStat.date == date))
    return result.scalar_one_or_none() or 0


async def get_counts_for_dates(session: AsyncSession, dates: list[str]) -> dict[str, int]:
    result = await session.execute(select(RequestStat.date, RequestStat.count).where(RequestStat.date.in_(dates)))
    return dict(result.all())


async def count_users(session: AsyncSession) -> int:
    result = await session.execute(select(func.count()).select_from(User))
    return result.scalar_one()


async def count_notes(session: AsyncSession) -> int:
    result = await session.execute(select(func.count()).select_from(Note))
    return result.scalar_one()


async def count_published_notes(session: AsyncSession) -> int:
    result = await session.execute(select(func.count()).select_from(Note).where(Note.is_public.is_(True)))
    return result.scalar_one()
