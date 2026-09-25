"""Business logic for the slug-redirect feature.

Three concerns live here:
  1. Setting/replacing a slug for a published note or folder (owner-only,
     the target must be published at the time of setting).
  2. Checking whether a slug is globally available.
  3. Resolving a slug to its target type + id (public, no auth).

The "target must be published" rule is enforced here rather than in the
router so it runs regardless of how the caller reaches this code. We
deliberately do NOT auto-delete a slug when content is unpublished via the
notes/folders routers — that would require every publish-toggle path to
import this module, creating circular-ish dependency chains for a rare
edge case. Instead, the public resolution endpoint (resolve_slug below)
re-checks is_public at read time and 404s if the target is no longer
public, so stale slug rows are harmless. The owner can reclaim the slug
or set a new one after republishing.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from ...core.exceptions import BadRequestError, ConflictError, NotFoundError
from ...core.config import get_settings
from ...shared.ids import parse_uuid
from . import repository
from .schemas import SlugAvailability, SlugOut, SlugResolve


def _short_url(slug: str) -> str:
    settings = get_settings()
    return f"{settings.frontend_base_url}/p/s/{slug}"


async def set_note_slug(
    db: AsyncSession, owner_id: uuid.UUID, note_id_str: str, slug: str
) -> SlugOut:
    from ...modules.notes.repository import find_by_id as find_note

    note_uuid = parse_uuid(note_id_str, BadRequestError("Invalid note id"))
    note = await find_note(db, owner_id, note_uuid)
    if not note:
        raise NotFoundError("Note not found")
    if not note.is_public:
        raise BadRequestError("Only published notes can have a custom short URL. Publish the note first.")

    # Global uniqueness check: slug must not be claimed by *any* other target.
    existing = await repository.find_by_slug(db, slug)
    if existing and existing.target_id != note_uuid:
        raise ConflictError("That URL is already taken. Please choose a different one.")

    row = await repository.upsert(db, owner_id, slug, "note", note_uuid)
    return SlugOut(
        slug=row.slug,
        target_type="note",
        target_id=str(note_uuid),
        short_url=_short_url(row.slug),
    )


async def set_folder_slug(
    db: AsyncSession, owner_id: uuid.UUID, folder_id_str: str, slug: str
) -> SlugOut:
    from ...modules.folders.repository import find_by_id as find_folder

    folder_uuid = parse_uuid(folder_id_str, BadRequestError("Invalid folder id"))
    folder = await find_folder(db, owner_id, folder_uuid)
    if not folder:
        raise NotFoundError("Folder not found")
    if not folder.is_public:
        raise BadRequestError("Only published folders can have a custom short URL. Publish the folder first.")

    existing = await repository.find_by_slug(db, slug)
    if existing and existing.target_id != folder_uuid:
        raise ConflictError("That URL is already taken. Please choose a different one.")

    row = await repository.upsert(db, owner_id, slug, "folder", folder_uuid)
    return SlugOut(
        slug=row.slug,
        target_type="folder",
        target_id=str(folder_uuid),
        short_url=_short_url(row.slug),
    )


async def get_note_slug(
    db: AsyncSession, owner_id: uuid.UUID, note_id_str: str
) -> SlugOut | None:
    """Return the current slug for a note, or None if none has been set."""
    from ...modules.notes.repository import find_by_id as find_note

    note_uuid = parse_uuid(note_id_str, BadRequestError("Invalid note id"))
    note = await find_note(db, owner_id, note_uuid)
    if not note:
        raise NotFoundError("Note not found")

    row = await repository.find_by_target(db, "note", note_uuid)
    if not row:
        return None
    return SlugOut(
        slug=row.slug,
        target_type="note",
        target_id=str(note_uuid),
        short_url=_short_url(row.slug),
    )


async def get_folder_slug(
    db: AsyncSession, owner_id: uuid.UUID, folder_id_str: str
) -> SlugOut | None:
    """Return the current slug for a folder, or None if none has been set."""
    from ...modules.folders.repository import find_by_id as find_folder

    folder_uuid = parse_uuid(folder_id_str, BadRequestError("Invalid folder id"))
    folder = await find_folder(db, owner_id, folder_uuid)
    if not folder:
        raise NotFoundError("Folder not found")

    row = await repository.find_by_target(db, "folder", folder_uuid)
    if not row:
        return None
    return SlugOut(
        slug=row.slug,
        target_type="folder",
        target_id=str(folder_uuid),
        short_url=_short_url(row.slug),
    )


async def check_availability(db: AsyncSession, slug: str) -> SlugAvailability:
    """Global availability check — no auth needed (the dialog uses this
    while the user is still typing, before they hit Save)."""
    existing = await repository.find_by_slug(db, slug)
    return SlugAvailability(slug=slug, available=existing is None)


async def resolve_slug(db: AsyncSession, slug: str) -> SlugResolve:
    """Public: resolve a slug to its target type + id. Re-validates that
    the target is still published so a slug pointing at unpublished content
    404s cleanly instead of returning a target the reader can't access."""
    row = await repository.find_by_slug(db, slug)
    if not row:
        raise NotFoundError("Short URL not found")

    if row.target_type == "note":
        from ...modules.public.repository import find_public_note
        note = await find_public_note(db, row.target_id)
        if not note:
            raise NotFoundError("Short URL not found")
    elif row.target_type == "folder":
        from ...modules.public.repository import find_public_folder
        folder = await find_public_folder(db, row.target_id)
        if not folder:
            raise NotFoundError("Short URL not found")
    else:
        raise NotFoundError("Short URL not found")

    return SlugResolve(target_type=row.target_type, target_id=str(row.target_id))
