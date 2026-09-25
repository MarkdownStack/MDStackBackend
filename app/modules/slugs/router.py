"""HTTP binding for slug-redirect routes.

Two groups:
  - Authenticated (/api/slugs/*): set or read the slug for your own
    published content.
  - Public (/api/public/s/{slug}): resolve a slug to its target — no auth,
    used by the frontend's /p/s/:slug route to decide where to navigate.

The availability check (GET /api/slugs/check/{slug}) is intentionally
unauthenticated — the slug dialog debounces against it while the user is
still typing, before they've committed, and requiring auth there would mean
the request either needs the auth header (fine, the page has it) or a
separate unauthed endpoint. Keeping it under /api/slugs/ with no Depends
on get_current_user is the simpler choice; slug values themselves contain
no private information.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.postgres import get_db
from ...shared.dependencies import get_current_user
from . import service
from .schemas import SlugAvailability, SlugOut, SlugResolve, SlugSet

router = APIRouter(tags=["slugs"])


# ---- Authenticated: manage slugs for your own content --------------------

@router.put("/api/slugs/note/{note_id}", response_model=SlugOut)
async def set_note_slug(
    note_id: str,
    payload: SlugSet,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await service.set_note_slug(db, current_user["_id"], note_id, payload.slug)


@router.put("/api/slugs/folder/{folder_id}", response_model=SlugOut)
async def set_folder_slug(
    folder_id: str,
    payload: SlugSet,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await service.set_folder_slug(db, current_user["_id"], folder_id, payload.slug)


@router.get("/api/slugs/note/{note_id}", response_model=SlugOut | None)
async def get_note_slug(
    note_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Returns the current slug for this note, or null if none has been set."""
    return await service.get_note_slug(db, current_user["_id"], note_id)


@router.get("/api/slugs/folder/{folder_id}", response_model=SlugOut | None)
async def get_folder_slug(
    folder_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Returns the current slug for this folder, or null if none has been set."""
    return await service.get_folder_slug(db, current_user["_id"], folder_id)


# ---- Unauthenticated: availability check (used by the slug dialog) -------

@router.get("/api/slugs/check/{slug}", response_model=SlugAvailability)
async def check_slug_availability(slug: str, db: AsyncSession = Depends(get_db)):
    """Global availability check — no auth needed. The slug dialog calls
    this while the user is typing so they get instant feedback before
    hitting Save."""
    return await service.check_availability(db, slug)


# ---- Public: resolve a slug to its target --------------------------------

@router.get("/api/public/s/{slug}", response_model=SlugResolve)
async def resolve_slug(slug: str, db: AsyncSession = Depends(get_db)):
    """Resolve a custom short URL to its target type + id. The frontend's
    /p/s/:slug route calls this and then navigates to the appropriate
    reader page (/p/:noteId or /p/folder/:folderId). Returns 404 if the
    slug doesn't exist or the target is no longer published."""
    return await service.resolve_slug(db, slug)
