"""Aggregate router — includes every module's router (plus, for now, every
not-yet-migrated router under app/routers/, per PLAN.md's Phase 3). main.py
includes just this one router, so it doesn't need to change again as each
remaining module migrates — only this file does, one import swapped at a
time.

Include order is preserved exactly from the original app/main.py: auth
(now users), notes, folders, search, tags, upload, public, export, admin.
"""

from fastapi import APIRouter

from .modules.notes.router import router as notes_router
from .modules.users.router import router as users_router
from .routers import admin, export, folders, public, search, tags, upload

api_router = APIRouter()

api_router.include_router(users_router)
api_router.include_router(notes_router)
api_router.include_router(folders.router)
api_router.include_router(search.router)
api_router.include_router(tags.router)
api_router.include_router(upload.router)
api_router.include_router(public.router)
api_router.include_router(export.router)
api_router.include_router(admin.router)
