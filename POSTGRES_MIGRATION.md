# MongoDB → PostgreSQL migration

This backend was fully rewired from MongoDB (Motor async driver) to
PostgreSQL (SQLAlchemy 2.0 async ORM + asyncpg). This is a **full code
migration**, not just a schema design exercise — every router, service,
and repository now reads/writes Postgres. There was no existing
production data to carry over, so this is a fresh-start migration: there
is no Mongo→Postgres data export/import script.

## Why

The original data model stored users, folders, and notes as loosely
related Mongo documents (folders/notes scoped by a free-text
`owner_id`/`folder_path` string, tags as a plain array on the note
document, user preferences living only in frontend `localStorage`). This
migration makes the relationships explicit as foreign keys and adds a
real `user_preferences` table backing settings that previously had no
server-side home at all.

## Entity relationships

```
User 1───1 UserPreferences   (shared primary key: user_preferences.user_id)
User 1───* Folder            (folders.owner_id)
User 1───* Note              (notes.owner_id)
Folder 1───* Note            (notes.folder_id — NULLABLE, see below)
Note  *───* Tag              (through note_tags association table)
Note 1───* Comment           (comments.note_id)
User 1───* Comment           (comments.owner_id — the real commenting account)
```

- **User → Folder / Note**: every folder and note has exactly one owning
  user (`ON DELETE CASCADE` — deleting a user removes their folders,
  notes, tags, comments, and preferences row).
- **User ↔ UserPreferences**: one-to-one via a shared primary key
  (`user_preferences.user_id` is both PK and FK). A row is created
  automatically at registration (`modules/users/service.py::register`),
  so every user always has exactly one preferences row — no lazy-create
  branch needed at read time.
- **Folder → Note**: `notes.folder_id` is a **nullable** FK, not a
  required one. The old Mongo model scoped notes by a free-text
  `folder_path` that didn't always have a backing folder document (an
  "implied" folder — e.g. one that only exists because a note's path
  implies it, with no folder ever explicitly created at that path).
  `folder_path` is kept as its own column for the same reason and is
  still what folder-subtree queries scope by (see "No regex" below), not
  the FK — an implied subfolder several levels deep may have no `Folder`
  row of its own either.
- **Note ↔ Tag**: many-to-many through `note_tags`, replacing Mongo's
  plain `tags: []` array on the note document. Tags are scoped per-owner
  (the same tag text used by two accounts is two distinct rows — this is
  private-vault metadata, not a shared taxonomy). Read paths order tags
  alphabetically for a deterministic result, since the many-to-many join
  doesn't preserve "insertion order" the way a Mongo array did.
- **Note → Comment**, **User → Comment**: a comment always has both a
  note and a real owning user — no anonymous/free-typed comment authors,
  matching the previous behavior.

## Primary keys: UUID

All tables use `uuid.UUID` primary keys (Postgres native `UUID` type,
generated client-side via `uuid.uuid4()`), not auto-increment integers.
The old Mongo `ObjectId` was already an opaque id string as far as the
API contract goes (`NoteOut.id: str`, etc.), so this keeps that contract
unchanged — nothing calling this API needs to change just because ids
went from 24-hex-char ObjectIds to 36-character UUID strings.

## Markdown content: `Text`, not `String(n)`

`notes.content` and `comments.content` use the unbounded Postgres `Text`
type, not a length-capped `String`, matching the migration brief's
requirement and Mongo's original schemaless string storage. There's no
practical size limit on note/comment content as a result of this
migration.

## Full-text search (replacing Mongo `$text`)

`notes.search_vector` is a **stored, computed column**:

```python
search_vector: Mapped[str] = mapped_column(
    TSVECTOR,
    Computed(
        "to_tsvector('english', coalesce(title, '') || ' ' || coalesce(content, ''))",
        persisted=True,
    ),
    nullable=True,
)
```

Postgres recomputes it automatically on every insert/update — the
application never writes to it directly. Search queries
(`modules/notes/repository.py::text_search`) use
`plainto_tsquery('english', :query)` against this column via the `@@`
operator, ranked with `ts_rank`, backed by a GIN index
(`ix_notes_search_vector_gin`). This is Postgres's own tokenizer/stemmer
pipeline, not a regular expression, and is unrelated to the regex removal
described below.

## "Avoid regex completely"

Per the migration brief, no code path introduced or touched by this
migration uses Python's `re` module. Two pieces of the original codebase
did rely on regex and were rewritten as explicit, non-regex logic:

1. **`shared/markdown.py`** — `extract_links` (wikilink `[[Target]]` /
   `[[Target|Display]]` parsing), `extract_tags` (`#tag` extraction), and
   `excerpt` generation were reimplemented as character-scanning state
   machines instead of regex matches. `extract_links` in particular needed
   a small state machine (`_find_first_of`) to correctly reject malformed
   input like `[[Note#Section]]` (a hash before the close is a hard
   non-match) and stray brackets like `"[[A][[B]]"` (must find only "B",
   not "A][[B"). Both were verified byte-for-byte identical to the
   original regex-based behavior via curated edge cases and a 3,000-case
   property-based fuzz test before being accepted.

2. **`shared/paths.py`** — folder-subtree scoping (previously built on a
   `re.escape()`-constructed pattern for Mongo's `$regex` queries) is now
   `folder_scope_clause(column, path)`, which escapes `%`, `_`, and `\`
   manually and returns a SQLAlchemy `OR(column == path, column LIKE
   '<escaped_path>/%' ESCAPE '\')` clause — plain SQL `LIKE`, not a regex
   engine at all. `path_in_scope` (the equivalent in-Python check) is a
   plain string comparison, replacing the one `re.match()` call site.

## Timestamps: no `onupdate`, set explicitly in Python

Every `updated_at` column (`users`, `notes`, `comments`,
`user_preferences`) uses `server_default=func.now()` for insert time only
— there is **no** `onupdate=func.now()` trigger. This was a deliberate
fix, not an oversight: under async SQLAlchemy, a server-computed
`onupdate` value comes back "expired" after an `UPDATE`, and a later plain
attribute read on that expired attribute triggers an implicit lazy
refresh that async SQLAlchemy cannot perform outside an explicit
`await session.refresh(...)`, raising `sqlalchemy.exc.MissingGreenlet:
greenlet_spawn has not been called`. Every write path that should bump
`updated_at` now sets it explicitly instead —
`entity.updated_at = datetime.now(timezone.utc)` — the same app-managed
timestamp control the Mongo version always had (`updated_at: now_iso()`
on every `$set`). `Folder.created_at`/`updated_at` remain nullable with
no server default at all, preserving the existing behavior that a folder
created implicitly (e.g. as an ancestor path during upload) never gets
timestamps, unlike an explicitly created one.

## Raw SQL gotcha (request_stats upsert)

`core/middleware.py`'s traffic-counter upsert uses a raw `text()` SQL
statement with a bind parameter cast inside `jsonb_build_object()`. Note
the parenthesization: `(:method)::text`, not `:method::text`. Without the
parens, SQLAlchemy's `text()` parser treats `name::type` as a literal
Postgres cast syntax and does **not** substitute `:method` as a bind
parameter at all — this fails loudly as a syntax error in some contexts,
but can also silently produce wrong results with no exception if the
statement is otherwise syntactically valid. Any new raw SQL added to this
codebase with a bind parameter immediately followed by `::` should use the
parenthesized form.

## One-time data migration script

This migration itself was code-only, fresh-start (no data carried over
automatically). If there's real data still sitting in the old MongoDB
Atlas cluster you want in the new database, `scripts/migrate_mongo_to_postgres.py`
does that carry-over as a separate, explicit step — run once, against an
empty Postgres schema:

```bash
cd backend
uv run --with 'pymongo[srv]' python scripts/migrate_mongo_to_postgres.py            # dry run first
uv run --with 'pymongo[srv]' python scripts/migrate_mongo_to_postgres.py --apply     # then for real
```

`pymongo` is deliberately not a project dependency — it's added just for
this one run via uv's `--with`, rather than reintroducing a Mongo driver
into `pyproject.toml`/`uv.lock` for a script that's meant to run exactly
once. It reads `MONGO_URL`/`DB_NAME` from `backend/.env` (the same
variables the old backend used) and `DATABASE_URL` the same way the app
itself does.

It's a straight, non-upsert insert: every row gets a fresh UUID assigned
in Python, with foreign keys filled in from an id-mapping table built
while walking the Mongo collections in dependency order (users → folders
→ notes/tags → comments). Because ids are never database-generated, the
whole thing runs as one transaction — the default is a dry run (rolled
back at the end so you can check the printed counts first), and it
refuses outright to touch a Postgres database that already has rows in
`users` unless you pass `--force`.

It also replays every documented Mongo quirk explicitly rather than
assuming a clean shape: a legacy user with no `username` field at all, a
folder auto-created by upload's `ensure_folder_chain` with no
`created_at`/`updated_at` at all, a note created via `/api/upload` with
no `is_public`/`upvotes`/`downvotes` fields at all, and the flat `tags: []`
string array on each note getting normalized into deduped `Tag` rows and
`note_tags` links (per-owner, and per-note). A record referencing an
owner/note that no longer exists is skipped and reported by id rather
than aborting the run. This was verified against a fake dataset built to
hit every one of those cases, run end-to-end into a real local Postgres
database, before being handed over.

`request_stats` (the admin traffic counter) is included by default since
it's easy and complete, but it's pure derived analytics, not vault
content — pass `--skip-request-stats` to just let it start fresh instead.

## Behavior changes worth knowing about

- **Tag order**: tags on a note are now returned alphabetically (a
  property of the many-to-many join), not in the insertion/typed order a
  Mongo array preserved.
- **Search engine**: full-text search now uses Postgres's English
  stemmer/tokenizer (`to_tsvector`/`plainto_tsquery`) instead of Mongo's
  `$text` index — ranking and matching behavior (e.g. stemming edge
  cases, stopword handling) may differ slightly for the same query.
- **Vote counting**: `public/repository.py::vote_note` was simplified from
  a SQL-expression update (`func.greatest(0, ...)`) to a plain Python
  `max(0, note.upvotes + up_delta)` assignment — functionally identical,
  but avoids needing a post-update refresh, and confirmed to still never
  touch `updated_at` on a vote (matching prior behavior).

## Environment / infrastructure changes

- `.env.example` / `Settings`: `MONGO_URL` + `DB_NAME` → single
  `DATABASE_URL` (SQLAlchemy async URL, e.g.
  `postgresql+asyncpg://mdstack:mdstack@localhost:5432/mdstack`).
  **The commented-out MongoDB Atlas credential block at the bottom of
  `.env.example` was left untouched** — see the code comment directly
  above it; that credential is real and known to the project owner, who
  will rotate it separately.
- `docker-compose.yml`: added a `postgres` service (`postgres:16-alpine`,
  named volume `pgdata`); `backend` now depends on it and gets
  `DATABASE_URL` pointed at the compose-network hostname `postgres`
  instead of `localhost`.
- `pyproject.toml` / `uv.lock`: removed `motor`; added
  `sqlalchemy[asyncio]`, `asyncpg`, `alembic`.
- **Alembic** is now set up (`alembic/`, async template). `alembic/env.py`
  reads `DATABASE_URL` from the app's own `Settings` object
  (`app/core/config.py`) rather than a separately maintained URL in
  `alembic.ini` — there is exactly one place this app's Postgres
  connection string is configured. The initial migration
  (`alembic/versions/eb47cadd9123_initial_schema.py`) creates all 9
  tables (`users`, `user_preferences`, `folders`, `tags`, `notes`,
  `note_tags`, `comments`, `request_stats`, plus Alembic's own
  `alembic_version`) and was verified to apply cleanly to a fresh
  database with zero drift afterward (a follow-up
  `alembic revision --autogenerate` produced no operations).

## Running it

```bash
# start Postgres (or point DATABASE_URL at an existing instance)
docker compose up -d postgres

# apply the schema
cd backend
DATABASE_URL=postgresql+asyncpg://mdstack:mdstack@localhost:5432/mdstack \
  uv run alembic upgrade head

# run the app as usual — app/main.py's lifespan no longer touches Mongo
uv run uvicorn app.main:app --reload
```

To generate a new migration after changing `app/db/models.py`:

```bash
DATABASE_URL=postgresql+asyncpg://mdstack:mdstack@localhost:5432/mdstack \
  uv run alembic revision --autogenerate -m "describe the change"
```

## Retired Mongo modules

`app/db/mongo.py`, `app/db/collections.py`, `app/db/indexes.py`, and
`app/shared/objectid.py` are left in place as thin stub files that
`raise ImportError(...)` with a docstring pointing at their Postgres
replacement, matching this codebase's own established convention for
retiring a module in place rather than deleting it outright (see
`SKILL.md`'s history section for prior examples of this pattern).
