"""Business logic for folders: listing, creation, recursive cascade
delete, publish, and the "my published folders" listing — moved from
app/routers/folders.py. Behavior unchanged; HTTPException is replaced with
the equivalent domain exception from core/exceptions.py."""

from ...core.exceptions import BadRequestError, ConflictError, NotFoundError
from ...modules.public.schemas import PublicFolderSummary
from ...modules.users.repository import authors_by_owner_id
from ...shared.datetime import now_iso
from ...shared.paths import folder_scope_pattern, normalize_folder_path
from . import repository
from .models import to_folder_out
from .schemas import FolderOut, FolderPublishUpdate


async def list_folders(owner_id: str) -> dict:
    """Return every known folder path for this user (explicitly created OR implied by a note)."""
    explicit = await repository.list_explicit_paths(owner_id)
    implied = await repository.list_implied_paths(owner_id)
    all_paths = sorted(p for p in (explicit | implied) if p)
    return {"paths": all_paths}


async def create_folder(owner_id: str, path: str) -> dict:
    path = normalize_folder_path(path)
    if not path:
        raise BadRequestError("Folder path cannot be empty")
    if await repository.find_by_path(owner_id, path):
        raise ConflictError("Folder already exists")
    ts = now_iso()
    await repository.insert(owner_id, path, ts)
    return {"path": path, "created_at": ts, "updated_at": ts}


async def delete_folder(owner_id: str, path: str) -> dict:
    """Delete a folder and cascade: every note directly inside it, every
    note inside any of its subfolders, and the subfolders themselves all go
    with it. There's no recycle bin for this, so the frontend is expected to
    confirm with the user before calling this — see Sidebar.jsx."""
    path = normalize_folder_path(path)
    if not path:
        raise BadRequestError("Cannot delete the vault root")

    # Anchored + escaped so this matches `path` itself and anything nested
    # under it (`path/...`) but never a sibling that merely starts with the
    # same characters — e.g. deleting "notes" must not touch "notes-archive".
    pattern = folder_scope_pattern(path)

    # Folders aren't always backed by an explicit folders_collection doc —
    # one implied purely by a note's folder_path (never separately created,
    # never touched by ensure_folder_chain) still shows up in the sidebar
    # tree, so "not found" has to mean "nothing at all lives at this path",
    # not just "no explicit folder doc".
    has_folder_doc = await repository.find_one_folder_matching_scope(owner_id, pattern)
    has_notes = await repository.find_one_note_matching_scope(owner_id, pattern)
    if not has_folder_doc and not has_notes:
        raise NotFoundError("Folder not found")

    deleted_notes, deleted_folders = await repository.delete_scope(owner_id, pattern)
    return {"path": path, "deleted_notes": deleted_notes, "deleted_folders": deleted_folders}


async def list_my_published_folders(owner_id: str) -> list[PublicFolderSummary]:
    """Every folder this user has published, in the same card shape
    (PublicFolderSummary) as the anonymous Explore feed's "published
    folders" listing — backs both the sidebar's globe badge/toggle state
    (which only needs `path`/`id`) and "My published notes"'s own "My
    published folders" section (which needs the rest: `name`, `note_count`,
    `updated_at`), the same way modules/notes' list_my_published_notes
    already reuses PublicNoteSummary's shape for its own notes grid."""
    docs = await repository.list_published(owner_id)

    authors = await authors_by_owner_id({owner_id})
    author = authors.get(owner_id, "Someone")

    summaries = []
    for doc in docs:
        path = doc["path"]
        count = await repository.count_notes_matching_scope(owner_id, folder_scope_pattern(path))
        summaries.append(
            PublicFolderSummary(
                id=str(doc["_id"]),
                name=path.split("/")[-1],
                path=path,
                author=author,
                note_count=count,
                updated_at=doc.get("updated_at", ""),
            )
        )
    return summaries


async def set_folder_publish(owner_id: str, path: str, payload: FolderPublishUpdate) -> FolderOut:
    """Folder-level publish: toggles a whole folder — and every note nested
    under it, at any depth — visible at a no-login-required URL, the same
    idea as a note's own Publish toggle in NoteEditor but one level up.
    Deliberately independent of any individual note's `is_public` flag:
    publishing a folder doesn't touch the notes inside it, so unpublishing
    the folder later can't accidentally leave a note dangling public
    elsewhere (e.g. still listed in Explore), and vice versa — see
    modules/public's get_public_folder for how a note's visibility here is
    resolved purely from the folder's own published subtree at read time,
    not from any flag stored on the note itself.

    A folder doc doesn't always exist yet (see list_folders' explicit-vs-
    implied comment above — a folder can be "real" purely because a note's
    folder_path points at it), so this upserts one rather than requiring
    create_folder to have been called first.
    """
    path = normalize_folder_path(path)
    if not path:
        raise BadRequestError("Cannot publish the vault root")
    ts = now_iso()
    doc = await repository.upsert_publish(owner_id, path, payload.is_public, ts)
    return to_folder_out(doc, ts)
