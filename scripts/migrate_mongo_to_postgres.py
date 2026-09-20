"""One-time data migration: MongoDB Atlas -> Postgres.

Run this once, after `alembic upgrade head` has created an empty Postgres
schema, to carry over whatever real data is still sitting in the old Mongo
Atlas cluster (see backend/SKILL.md's "Data model" section for the
authoritative description of the Mongo shapes this script assumes).

WHY IT'S SHAPED THIS WAY
-------------------------
- All Mongo reads happen up front with plain pymongo (sync), fully
  in-memory, before any Postgres write starts. There's no need for an
  async Mongo driver here — motor was removed from this project's own
  dependencies as part of the Postgres migration, and this script is a
  one-off ops tool, not app code, so it reaches for plain pymongo instead
  of reintroducing motor as a real dependency.
- Every new Postgres row gets its UUID primary key assigned in Python
  *before* it's added to the session (see `uuid4()` calls below), and
  every foreign key is filled in from an in-memory id-mapping dict built
  while walking the Mongo collections in dependency order (users ->
  folders -> notes/tags -> comments). Because the ids are never
  database-generated, there's no need to flush between phases just to
  learn a new id back — the whole migration commits in one transaction.
- Old Mongo timestamps were written as ISO-8601 strings via
  `shared/datetime.py`'s `now_iso()` (`datetime.now(timezone.utc)
  .isoformat()`), not native BSON dates, so `_parse_dt` below parses
  strings first and only falls back to handling a native `datetime` for
  any stray early-dev-era document that might predate that convention.
- Fields that Mongo only ever *sometimes* wrote (`username`,
  `verification_token`, a folder's `created_at`/`updated_at` when it was
  auto-created by `ensure_folder_chain`, `is_public`/`upvotes`/`downvotes`
  on a note created via `/api/upload`) are read with `.get(...)` and a
  default that matches what every existing read path in the old codebase
  already assumed — never a bare `doc["field"]`.
- This only INSERTS. It doesn't upsert or dedupe, so it's only meant to
  run once against an empty schema — hence the safety check up front that
  refuses to run against a Postgres database that already has rows in it
  (override with --force if you really mean it), and the --dry-run mode
  (the default) that does the whole thing inside a transaction that's
  rolled back at the end instead of committed, so you can sanity-check
  the counts before actually committing with --apply.

USAGE
-----
Run from the `backend/` directory so `app.*` imports resolve and the
default `.env` lookup finds the right file. This script needs `pymongo`,
which is deliberately NOT a project dependency (motor/pymongo were
removed entirely from pyproject.toml by the Postgres migration) — add it
just for this one run with uv's `--with`, instead of touching
pyproject.toml/uv.lock for a script you'll run once:

    cd backend
    uv run --with 'pymongo[srv]' python scripts/migrate_mongo_to_postgres.py            # dry run
    uv run --with 'pymongo[srv]' python scripts/migrate_mongo_to_postgres.py --apply     # for real

Reads MONGO_URL/DB_NAME from backend/.env (the same file the old Mongo
backend used) unless overridden with --mongo-url/--mongo-db. Reads
DATABASE_URL the same way the app itself does (app.core.config.Settings)
unless overridden with --database-url.

Other flags:
    --sample N        Only migrate the first N documents of each Mongo
                       collection (fast smoke test before a real run).
    --skip-request-stats
                       Don't migrate the admin traffic-counter collection
                       (it's derived/analytics data, not vault content —
                       safe to skip and let it start fresh).
    --force            Proceed even if the target Postgres tables already
                       have rows in them. Dangerous with real data in
                       both places; only pass this if you know why.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(BACKEND_ROOT / ".env")

import pymongo  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.models import (  # noqa: E402
    Base,
    Comment,
    Folder,
    Note,
    RequestStat,
    Tag,
    User,
    UserPreferences,
    note_tags,
)


def _parse_dt(value) -> datetime | None:
    """Old Mongo docs store timestamps as ISO-8601 strings (see module
    docstring). Handle that, a stray native datetime, or a missing/empty
    value gracefully rather than raising mid-migration."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value)
        except ValueError:
            print(f"  ! could not parse timestamp {value!r}, treating as missing", file=sys.stderr)
            return None
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return None


def _limited(cursor, sample: int | None):
    return cursor.limit(sample) if sample else cursor


class Migration:
    def __init__(self, mongo_db, sample: int | None, skip_request_stats: bool):
        self.mongo_db = mongo_db
        self.sample = sample
        self.skip_request_stats = skip_request_stats

        # Mongo _id (str) -> new Postgres UUID
        self.user_id_map: dict[str, uuid.UUID] = {}
        self.folder_id_map: dict[str, uuid.UUID] = {}
        self.note_id_map: dict[str, uuid.UUID] = {}
        # (owner_uuid, folder path) -> folder UUID, for linking Note.folder_id
        # to a *real* Folder row when one exists at that exact path (see
        # db/models.py's Note docstring on why this is nullable/best-effort).
        self.folder_path_lookup: dict[tuple[uuid.UUID, str], uuid.UUID] = {}
        # (owner_uuid, tag name) -> tag UUID, built while walking notes.
        self.tag_cache: dict[tuple[uuid.UUID, str], uuid.UUID] = {}

        self.users: list[User] = []
        self.preferences: list[UserPreferences] = []
        self.folders: list[Folder] = []
        self.notes: list[Note] = []
        self.tags: list[Tag] = []
        self.note_tag_rows: list[dict] = []
        self.comments: list[Comment] = []
        self.request_stats: list[RequestStat] = []

        self.skipped: list[str] = []

    def load_users(self) -> None:
        coll = self.mongo_db.users
        for doc in _limited(coll.find(), self.sample):
            new_id = uuid.uuid4()
            self.user_id_map[str(doc["_id"])] = new_id

            created_at = _parse_dt(doc.get("created_at")) or datetime.now(timezone.utc)
            updated_at = _parse_dt(doc.get("updated_at")) or created_at

            self.users.append(
                User(
                    id=new_id,
                    email=doc["email"],
                    username=doc.get("username"),
                    password_hash=doc["password_hash"],
                    is_verified=bool(doc.get("is_verified", False)),
                    verification_token=doc.get("verification_token"),
                    verification_token_expires=_parse_dt(doc.get("verification_token_expires")),
                    password_reset_token=doc.get("password_reset_token"),
                    password_reset_token_expires=_parse_dt(doc.get("password_reset_token_expires")),
                    created_at=created_at,
                    updated_at=updated_at,
                )
            )
            # Mongo never had a preferences collection at all (see
            # db/models.py's UserPreferences docstring) — every migrated
            # user gets the same lazily-created defaults a freshly
            # registered user gets today.
            self.preferences.append(UserPreferences(user_id=new_id))
        print(f"users: {len(self.users)} loaded")

    def load_folders(self) -> None:
        coll = self.mongo_db.folders
        skipped = 0
        for doc in _limited(coll.find(), self.sample):
            owner_uuid = self.user_id_map.get(str(doc.get("owner_id")))
            if owner_uuid is None:
                skipped += 1
                self.skipped.append(f"folder {doc['_id']}: owner_id {doc.get('owner_id')} not found in users")
                continue

            new_id = uuid.uuid4()
            self.folder_id_map[str(doc["_id"])] = new_id
            path = doc["path"]
            self.folder_path_lookup[(owner_uuid, path)] = new_id

            self.folders.append(
                Folder(
                    id=new_id,
                    owner_id=owner_uuid,
                    path=path,
                    # Missing entirely on a folder auto-created by upload's
                    # ensure_folder_chain — default False, same as every
                    # existing read path already assumed.
                    is_public=bool(doc.get("is_public", False)),
                    # Genuinely absent (not just falsy) on those same
                    # auto-created folders — stays NULL, matching the
                    # nullable columns in db/models.py.
                    created_at=_parse_dt(doc.get("created_at")),
                    updated_at=_parse_dt(doc.get("updated_at")),
                )
            )
        print(f"folders: {len(self.folders)} loaded, {skipped} skipped (orphaned owner_id)")

    def _get_or_create_tag(self, owner_uuid: uuid.UUID, name: str) -> uuid.UUID:
        key = (owner_uuid, name)
        tag_id = self.tag_cache.get(key)
        if tag_id is None:
            tag_id = uuid.uuid4()
            self.tag_cache[key] = tag_id
            self.tags.append(Tag(id=tag_id, owner_id=owner_uuid, name=name))
        return tag_id

    def load_notes(self) -> None:
        coll = self.mongo_db.notes
        skipped = 0
        for doc in _limited(coll.find(), self.sample):
            owner_uuid = self.user_id_map.get(str(doc.get("owner_id")))
            if owner_uuid is None:
                skipped += 1
                self.skipped.append(f"note {doc['_id']}: owner_id {doc.get('owner_id')} not found in users")
                continue

            new_id = uuid.uuid4()
            self.note_id_map[str(doc["_id"])] = new_id

            folder_path = doc.get("folder_path", "")
            folder_uuid = self.folder_path_lookup.get((owner_uuid, folder_path))

            created_at = _parse_dt(doc.get("created_at")) or datetime.now(timezone.utc)
            updated_at = _parse_dt(doc.get("updated_at")) or created_at

            self.notes.append(
                Note(
                    id=new_id,
                    owner_id=owner_uuid,
                    folder_id=folder_uuid,
                    folder_path=folder_path,
                    title=doc["title"],
                    content=doc.get("content", ""),
                    links=list(doc.get("links", [])),
                    # A note created via /api/upload never had these three
                    # fields written at all (see backend/SKILL.md's Data
                    # model note) — default exactly like every existing
                    # read path already did.
                    is_public=bool(doc.get("is_public", False)),
                    upvotes=int(doc.get("upvotes", 0)),
                    downvotes=int(doc.get("downvotes", 0)),
                    created_at=created_at,
                    updated_at=updated_at,
                    # search_vector is a DB-computed column (see
                    # db/models.py) — never set it from here.
                )
            )

            # Mongo stored tags as a plain string array on the note
            # document; normalize into the new Tag/note_tags many-to-many
            # here, deduping both within this note and per-owner globally.
            for tag_name in dict.fromkeys(doc.get("tags", [])):
                tag_uuid = self._get_or_create_tag(owner_uuid, tag_name)
                self.note_tag_rows.append({"note_id": new_id, "tag_id": tag_uuid})

        print(f"notes: {len(self.notes)} loaded, {skipped} skipped (orphaned owner_id)")
        print(f"tags: {len(self.tags)} distinct (owner, name) pairs")

    def load_comments(self) -> None:
        coll = self.mongo_db.comments
        skipped = 0
        for doc in _limited(coll.find(), self.sample):
            note_uuid = self.note_id_map.get(str(doc.get("note_id")))
            owner_uuid = self.user_id_map.get(str(doc.get("owner_id")))
            if note_uuid is None or owner_uuid is None:
                skipped += 1
                reason = "note_id" if note_uuid is None else "owner_id"
                self.skipped.append(f"comment {doc['_id']}: {reason} not found")
                continue

            created_at = _parse_dt(doc.get("created_at")) or datetime.now(timezone.utc)
            updated_at = _parse_dt(doc.get("updated_at")) or created_at

            self.comments.append(
                Comment(
                    id=uuid.uuid4(),
                    note_id=note_uuid,
                    owner_id=owner_uuid,
                    content=doc["content"],
                    upvotes=int(doc.get("upvotes", 0)),
                    created_at=created_at,
                    updated_at=updated_at,
                )
            )
        print(f"comments: {len(self.comments)} loaded, {skipped} skipped (orphaned note_id/owner_id)")

    def load_request_stats(self) -> None:
        if self.skip_request_stats:
            print("request_stats: skipped (--skip-request-stats)")
            return
        coll = self.mongo_db.request_stats
        for doc in _limited(coll.find(), self.sample):
            self.request_stats.append(
                RequestStat(
                    date=doc["_id"],
                    count=int(doc.get("count", 0)),
                    methods=dict(doc.get("methods", {})),
                )
            )
        print(f"request_stats: {len(self.request_stats)} loaded")

    def load_all(self) -> None:
        self.load_users()
        self.load_folders()
        self.load_notes()
        self.load_comments()
        self.load_request_stats()
        if self.skipped:
            print(f"\n{len(self.skipped)} record(s) skipped as orphaned:")
            for line in self.skipped:
                print(f"  - {line}")


async def _check_target_is_empty(session_factory) -> bool:
    async with session_factory() as session:
        result = await session.execute(select(User.id).limit(1))
        return result.first() is None


async def write_to_postgres(migration: Migration, database_url: str, apply: bool, force: bool) -> None:
    engine = create_async_engine(database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    if not force and not await _check_target_is_empty(session_factory):
        print(
            "\nRefusing to run: the target Postgres database already has rows in "
            "`users`. This script only inserts (no upsert/dedupe) and is meant "
            "for a one-time migration into an EMPTY schema. Pass --force if you "
            "really want to proceed anyway.",
            file=sys.stderr,
        )
        await engine.dispose()
        sys.exit(1)

    async with session_factory() as session:
        try:
            session.add_all(migration.users)
            await session.flush()
            print("flushed: users")

            session.add_all(migration.preferences)
            await session.flush()
            print("flushed: user_preferences")

            session.add_all(migration.folders)
            await session.flush()
            print("flushed: folders")

            session.add_all(migration.tags)
            await session.flush()
            print("flushed: tags")

            session.add_all(migration.notes)
            await session.flush()
            print("flushed: notes")

            if migration.note_tag_rows:
                await session.execute(note_tags.insert(), migration.note_tag_rows)
                print(f"flushed: note_tags ({len(migration.note_tag_rows)} links)")

            session.add_all(migration.comments)
            await session.flush()
            print("flushed: comments")

            session.add_all(migration.request_stats)
            await session.flush()
            print("flushed: request_stats")

        except Exception:
            await session.rollback()
            await engine.dispose()
            print("\nERROR during migration — everything rolled back, Postgres is unchanged.", file=sys.stderr)
            raise

        if apply:
            await session.commit()
            print("\nCOMMITTED. Postgres now has the migrated data.")
        else:
            await session.rollback()
            print("\nDRY RUN complete (nothing committed). Re-run with --apply to write for real.")

    await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="Actually commit (default is a dry run).")
    parser.add_argument("--force", action="store_true", help="Proceed even if target Postgres tables aren't empty.")
    parser.add_argument("--sample", type=int, default=None, help="Only migrate the first N docs per collection.")
    parser.add_argument("--skip-request-stats", action="store_true", help="Don't migrate request_stats.")
    parser.add_argument("--mongo-url", default=os.environ.get("MONGO_URL"))
    parser.add_argument("--mongo-db", default=os.environ.get("DB_NAME"))
    parser.add_argument("--database-url", default=None, help="Defaults to Settings.database_url (.env's DATABASE_URL).")
    args = parser.parse_args()

    if not args.mongo_url or not args.mongo_db:
        parser.error(
            "MONGO_URL/DB_NAME not found in the environment or backend/.env, and "
            "--mongo-url/--mongo-db weren't given. Nothing to read from."
        )

    database_url = args.database_url or get_settings().database_url

    print(f"Mongo:    {args.mongo_db} @ {args.mongo_url.split('@')[-1]}")  # never print credentials
    print(f"Postgres: {database_url.split('@')[-1]}")
    print(f"Mode:     {'APPLY (will commit)' if args.apply else 'DRY RUN (will roll back)'}")
    if args.sample:
        print(f"Sample:   first {args.sample} docs per collection only")
    print()

    mongo_client = pymongo.MongoClient(args.mongo_url, serverSelectionTimeoutMS=10_000)
    mongo_db = mongo_client[args.mongo_db]
    try:
        mongo_client.admin.command("ping")
    except Exception as exc:
        print(f"Could not reach MongoDB: {exc}", file=sys.stderr)
        sys.exit(1)

    migration = Migration(mongo_db, sample=args.sample, skip_request_stats=args.skip_request_stats)
    migration.load_all()
    mongo_client.close()

    print()
    asyncio.run(write_to_postgres(migration, database_url, apply=args.apply, force=args.force))


if __name__ == "__main__":
    main()
