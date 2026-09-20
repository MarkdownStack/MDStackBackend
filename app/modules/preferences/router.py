"""HTTP binding for /api/preferences — new module. GET returns (creating
lazily if needed) the caller's own settings row; PUT partially updates it.
Always scoped to the current account — there's no route to read or write
anyone else's preferences."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.postgres import get_db
from ...shared.dependencies import get_current_user
from . import service
from .schemas import PreferencesOut, PreferencesUpdate

router = APIRouter(prefix="/api/preferences", tags=["preferences"])


@router.get("", response_model=PreferencesOut)
async def get_preferences(current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await service.get_preferences(db, current_user["_id"])


@router.put("", response_model=PreferencesOut)
async def update_preferences(
    payload: PreferencesUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await service.update_preferences(db, current_user["_id"], payload)
