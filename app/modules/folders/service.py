"""Business logic for folders: listing, creation, recursive cascade
delete, rename, publish, and the "my published folders" listing. Behavior
unchanged from before this migration; every DB call now takes the
request's `AsyncSession` and ids are `uuid.UUID`."""

import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from ...core.exceptions import BadRequestError, ConflictError, NotFoundError
from ...modules.public.schemas import PublicFolderSummary
from ...modules.users.repository import authors_by_owner_id
from ...shared.datetime import iso
from ...shared.paths import normalize_folder_path
from . import repository
from .models import to_folder_out
from .schemas import FolderOut, FolderPublishUpdate


async def list_folders(db: AsyncSession, owner_id: uuid.UUID) -> dict:
    """Return every known folder path for this user (explicitly created OR implied by a note)."""
    explicit = await repository.list_explicit_paths(db, owner_id)
    implied = await repository.list_implied_paths(db, owner_id)
    all_paths = sorted(p for p in (explicit | implied) if p)
    return {"paths": all_paths}


async def create_folder(db: AsyncSession, owner_id: uuid.UUID, path: str) -> dict:
    path = normalize_folder_path(path)
    if not path:
        raise BadRequestError("Folder path cannot be empty")
    if await repository.find_by_path(db, owner_id, path):
        raise ConflictError("Folder already exists")
    ts = datetime.now(timezone.utc)
    await repository.insert(db, owner_id, path, ts)
    return {"path": path, "created_at": iso(ts), "updated_at": iso(ts)}


async def rename_folder(
    db: AsyncSession, owner_id: uuid.UUID, old_path: str, new_name: str
) -> dict:
    """Rename the last segment of a folder path.

    old_path = "python/advanced"
    new_name = "expert"
    → new_path = "python/expert"

    Every folder row whose path starts with old_path (exact match or
    old_path + "/") gets its path prefix rewritten. Every note whose
    folder_path is in that subtree gets the same rewrite. This keeps the
    tree consistent without a client-side full reload being strictly
    required (though bumpRefresh is still called so the sidebar re-sorts).

    Constraints checked:
    - new_name must be a non-empty string with no slashes (it's one segment).
    - The resulting new_path must not already exist for this owner.
    """
    old_path = normalize_folder_path(old_path)
    if not old_path:
        raise BadRequestError("Cannot rename the vault root")

    new_name = new_name.strip()
    if not new_name:
        raise BadRequestError("Folder name cannot be empty")
    if "/" in new_name:
        raise BadRequestError("Folder name cannot contain a slash — rename one segment at a time")

    # Build the new path by replacing only the last segment.
    parent = old_path.rsplit("/", 1)[0] if "/" in old_path else ""
    new_path = f"{parent}/{new_name}" if parent else new_name

    if old_path == new_path:
        # Nothing to do — same name.
        return {"old_path": old_path, "new_path": new_path}

    # Guard: the destination must not already exist.
    if await repository.find_by_path(db, owner_id, new_path):
        raise ConflictError(f'A folder named "{new_name}" already exists here')

    ts = datetime.now(timezone.utc)
    await repository.rename_scope(db, owner_id, old_path, new_path, ts)
    return {"old_path": old_path, "new_path": new_path}


async def delete_folder(db: AsyncSession, owner_id: uuid.UUID, path: str) -> dict:
    """Delete a folder and cascade: every note directly inside it, every
    note inside any of its subfolders, and the subfolders themselves all go
    with it. There's no recycle bin for this, so the frontend is expected to
    confirm with the user before calling this — see Sidebar.jsx."""
    path = normalize_folder_path(path)
    if not path:
        raise BadRequestError("Cannot delete the vault root")

    # Folders aren't always backed by an explicit Folder row — one implied
    # purely by a note's folder_path (never separately created, never
    # touched by ensure_folder_chain) still shows up in the sidebar tree,
    # so "not found" has to mean "nothing at all lives at this path", not
    # just "no explicit folder row".
    has_folder_row = await repository.find_one_folder_matching_scope(db, owner_id, path)
    has_notes = await repository.find_one_note_matching_scope(db, owner_id, path)
    if not has_folder_row and not has_notes:
        raise NotFoundError("Folder not found")

    deleted_notes, deleted_folders = await repository.delete_scope(db, owner_id, path)
    return {"path": path, "deleted_notes": deleted_notes, "deleted_folders": deleted_folders}


async def list_my_published_folders(db: AsyncSession, owner_id: uuid.UUID) -> list[PublicFolderSummary]:
    """Every folder this user has published, in the same card shape
    (PublicFolderSummary) as the anonymous Explore feed's "published
    folders" listing."""
    folders = await repository.list_published(db, owner_id)

    owner_id_str = str(owner_id)
    authors = await authors_by_owner_id(db, {owner_id_str})
    author = authors.get(owner_id_str, "Someone")

    summaries = []
    for folder in folders:
        count = await repository.count_notes_matching_scope(db, owner_id, folder.path)
        summaries.append(
            PublicFolderSummary(
                id=str(folder.id),
                name=folder.path.split("/")[-1],
                path=folder.path,
                author=author,
                note_count=count,
                updated_at=iso(folder.updated_at),
            )
        )
    return summaries


async def set_folder_publish(
    db: AsyncSession, owner_id: uuid.UUID, path: str, payload: FolderPublishUpdate
) -> FolderOut:
    """Folder-level publish: toggles a whole folder — and every note nested
    under it, at any depth — visible at a no-login-required URL. A folder
    row doesn't always exist yet (see list_folders' explicit-vs-implied
    comment above), so this upserts one rather than requiring create_folder
    to have been called first."""
    path = normalize_folder_path(path)
    if not path:
        raise BadRequestError("Cannot publish the vault root")
    ts = datetime.now(timezone.utc)
    folder = await repository.upsert_publish(db, owner_id, path, payload.is_public, ts)
    return to_folder_out(folder, iso(ts))
