"""Aggregate router — includes every module's router (plus, for now, every
not-yet-migrated router under app/routers/, per PLAN.md's Phase 3). main.py
includes just this one router, so it doesn't need to change again as each
remaining module migrates — only this file does, one import swapped at a
time.

Include order is preserved exactly from the original app/main.py: auth
(now users), notes, folders, search, tags, upload, public, export, admin.
"""

from fastapi import APIRouter

from .modules.comments.router import router as comments_router
from .modules.export.router import router as export_router
from .modules.folders.router import router as folders_router
from .modules.notes.router import router as notes_router
from .modules.public.router import router as public_router
from .modules.search.router import router as search_router
from .modules.tags.router import router as tags_router
from .modules.upload.router import router as upload_router
from .modules.users.router import router as users_router
from .routers import admin

api_router = APIRouter()

api_router.include_router(users_router)
api_router.include_router(notes_router)
api_router.include_router(folders_router)
api_router.include_router(search_router)
api_router.include_router(tags_router)
api_router.include_router(upload_router)
api_router.include_router(public_router)
api_router.include_router(comments_router)
api_router.include_router(export_router)
api_router.include_router(admin.router)
