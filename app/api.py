"""Aggregate router — includes every module's router.

Include order is preserved from before this migration: auth (users),
notes, folders, search, tags, upload, public, comments, export, admin.
`preferences` (new — see modules/preferences) is appended near the end.
`slugs` (new — see modules/slugs) is last: it mounts routes under both
/api/slugs/* (authenticated, owner-only slug management) and
/api/public/s/* (unauthenticated resolution), so it must come after the
public router to avoid route shadowing.
"""

from fastapi import APIRouter

from .modules.admin.router import router as admin_router
from .modules.comments.router import router as comments_router
from .modules.export.router import router as export_router
from .modules.folders.router import router as folders_router
from .modules.notes.router import router as notes_router
from .modules.preferences.router import router as preferences_router
from .modules.public.router import router as public_router
from .modules.search.router import router as search_router
from .modules.slugs.router import router as slugs_router
from .modules.tags.router import router as tags_router
from .modules.upload.router import router as upload_router
from .modules.users.router import router as users_router

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
api_router.include_router(admin_router)
api_router.include_router(preferences_router)
api_router.include_router(slugs_router)
