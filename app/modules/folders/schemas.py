"""Request/response models for folders — moved from app/models.py.

PublicFolderSummary (used by list_my_published_folders below, and by the
anonymous Explore feed) is deliberately NOT moved here — it's shared with
modules/public, which doesn't exist until a later Phase 3 step, so it
stays in app/models.py until that migration."""

from pydantic import BaseModel


class FolderCreate(BaseModel):
    path: str  # full path e.g. "projects/alpha"


class FolderOut(BaseModel):
    id: str | None = None
    path: str
    is_public: bool = False
    created_at: str
    updated_at: str


# Folder-level publish: the same idea as a note's own `is_public` toggle,
# one level up — makes an entire folder (and everything nested under it)
# reachable at a no-login-required URL, independent of whether any note
# inside it is individually published. See service.py.
class FolderPublishUpdate(BaseModel):
    is_public: bool
