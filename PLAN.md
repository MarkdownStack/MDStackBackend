# Backend restructure — domain modules + production hardening

> On approval this document gets written to `backend/PLAN.md` as the working checklist.

## Status: complete (2026-09-14)

Every phase below landed, each as its own commit on a stacked branch chain (`restructure/phase-1-core-db` → `phase-2-shared` → `phase-3-users` → `phase-3-notes` → `phase-3-folders` → `phase-3-public-comments` → `phase-3-search-tags` → `phase-3-upload-export` → `phase-3-admin`, then Phase 4's teardown on top). No route, status code, response body, or header changed — every phase was verified against a throwaway local MongoDB (never the real `.env`'s Atlas cluster) via full manual smoke passes, and the final state was verified with a real `docker build` + container run.

**Deliberate deviations from the plan below, both explained in their commit messages:**
- Phase 3's module order actually used was users → notes → folders → **public+comments together** → search+tags → upload+export → admin, not the plan's originally listed "users, comments, notes, folders, public, ...". Comments and public were combined into one migration step because today's code has every comment route living inside `public.py`, sharing its "is this note published" gate — splitting them into two sequential steps would have meant one briefly depending on a router file mid-deletion in the other.
- Automated test-writing (this plan's Phase 0) was explicitly deferred at the user's request ("don't write the tests right now") — every phase was still verified, just manually rather than via a committed pytest suite. `backend/SKILL.md`'s "Known open issues" tracks this as still open.

See `backend/SKILL.md` for the resulting architecture, kept up to date as the "read this first" doc — this file stays as the historical record of the restructure itself.

## Context

`backend/` is a live FastAPI + MongoDB service (`api.stalk-my-money.in`, deployed from `master` via `.github/workflows/deploy_ec2.yaml`). It is ~1,800 LOC organized **purely by technical layer**: one flat `app/routers/` package, one 299-line `app/models.py` holding every Pydantic schema in the product, and one `app/utils.py` mixing pure text helpers with Mongo-touching helpers.

That shape has already started costing:

- **No config layer.** `os.getenv` is called at *import time* in four separate modules (`auth.py`, `email.py`, `dependencies.py`, `database.py`). `backend/SKILL.md` records this as a gotcha already hit once — editing `.env` under a running `uvicorn` silently does nothing. Nothing validates or fails fast on a missing `JWT_SECRET_KEY`; it quietly falls back to `"dev-secret-change-me"`.
- **Routers do everything.** HTTP binding, business rules, and raw Motor queries live in the same function. `notes.py:101-124` builds a `$lookup` aggregation inline; `public.py` hand-rolls three different author-resolution call sites.
- **Duplication is already drifting.** `utils.py:42` defines `folder_scope_pattern()` with a comment explaining it exists so nobody reimplements it — and `export.py:69` reimplements it anyway. `oid()`/`InvalidId` handling is written twice (`notes.py:14`, `public.py:33`).
- **Mongo client is a module-level global** created at import (`database.py:10`) and never closed. There is no lifespan, and startup still uses the deprecated `@app.on_event("startup")`.
- **No tests, no linter.** The CI workflow's MongoDB + `pytest` steps are commented out and there is no suite behind them.

**Outcome:** reorganize `app/` **by domain/feature module**, add the config / lifespan / exception / logging / test layers the code currently lacks, and do it **without changing a single byte of externally observable behavior** — every URL, method, status code, response body, and error message stays identical.

## Non-negotiable guardrails

The frontend (`frontend/src/api/client.js`) and `mcp_server/` are both plain HTTP clients of this API. Neither imports `app/`. So the API surface *is* the contract, and it is frozen:

| Must not change | Why |
|---|---|
| Every path, method, status code, response shape | 29 call sites in the frontend + ~22 MCP tools |
| `{"detail": ...}` error body and `WWW-Authenticate: Bearer` on 401 | Frontend branches on `response.data.detail` and on 403-vs-401 at login |
| The enumeration-safe generic messages in `resend-verification` / `forgot-password` | Deliberate security design (`SKILL.md`) |
| `origins = ["*"]`; `CORS_ORIGINS` stays dead config | Wiring it live would break prod CORS depending on what EC2's `.env` holds. Flag only. |
| `get_current_user`'s no-DB-round-trip design | Documented perf decision |
| Fire-and-forget `asyncio.create_task` stats write | Documented latency decision |
| `MONGO_URL` default `"http:localhost:27017/"` | Preserve verbatim even though malformed — changing a default is a behavior change |
| The plaintext Mongo password + its warning comments in `.env.example` | Owner rotates on a call; do not remove, do not "clean up" |
| `app.main:app` importable at module level | `Dockerfile` CMD is `uvicorn app.main:app` |
| `Dockerfile` / `docker-compose.yml` locations | Everything stays under `app/`, so `COPY app ./app` still works. No CI or EC2 deploy changes. |

**No opportunistic fixes.** The N+1 `count_documents` loops (`public.py:256-270`, `folders.py:100-114`), the unbounded `list_notes`, and the missing pagination are *logged as follow-ups at the bottom*, not touched here. A restructure that also changes queries is a restructure you cannot bisect.

## Target structure

Adapted from the reference layout for **MongoDB, not SQLAlchemy** — there is no ORM and no Alembic, so `models.py` per module means *document shape + mappers*, and `repository.py` means *all Motor calls for that collection*.

```
backend/
├── app/
│   ├── main.py                 # create_app() factory + lifespan; module-level `app` preserved
│   ├── api.py                  # one aggregate APIRouter including every module router
│   │
│   ├── core/
│   │   ├── config.py           # pydantic-settings Settings + get_settings()
│   │   ├── security.py         # ← app/auth.py (bcrypt, JWT encode/decode)
│   │   ├── logging.py          # dictConfig + request-id log filter
│   │   ├── exceptions.py       # AppError hierarchy + global handlers
│   │   └── middleware.py       # ← app/middleware.py + RequestIdMiddleware
│   │
│   ├── db/
│   │   ├── mongo.py            # client lifecycle: connect() / close() / get_database()
│   │   ├── collections.py      # collection accessor functions (resolve post-connect)
│   │   └── indexes.py          # ← ensure_indexes(), assembled from per-module index specs
│   │
│   ├── modules/
│   │   ├── users/              # /api/auth  — register, login, verify, reset, /me
│   │   ├── notes/              # /api/notes — private CRUD, backlinks, published/mine
│   │   ├── folders/            # /api/folders — CRUD, cascade delete, folder publish
│   │   ├── comments/           # /api/public/notes/{id}/comments  (own collection → own module)
│   │   ├── public/             # /api/public — published notes + folders, voting
│   │   ├── search/             # /api/search — router + service only, reuses notes repo
│   │   ├── tags/               # /api/tags   — router + service only, reuses notes repo
│   │   ├── upload/             # /api/upload — bulk import
│   │   ├── export/             # /api/export — vault → streamed .zip
│   │   └── admin/              # /api/admin  — stats
│   │
│   └── shared/
│       ├── dependencies.py     # ← app/dependencies.py (get_current_user & friends)
│       ├── markdown.py         # ← utils.py: extract_tags / extract_links / excerpt
│       ├── paths.py            # ← utils.py: normalize_folder_path / folder_scope_pattern
│       ├── datetime.py         # ← models.py: now_iso
│       └── objectid.py         # the two duplicated oid()/InvalidId parsers, unified
│
├── tests/
│   ├── conftest.py
│   ├── contract/               # frozen route list + OpenAPI baseline
│   └── modules/                # per-module smoke + regression tests
│
├── Dockerfile                  # unchanged, stays here
└── docker-compose.yml          # unchanged, stays here
```

**Full module** = `router.py` + `schemas.py` + `models.py` + `service.py` + `repository.py`.
**Thin module** (`search`, `tags`) = `router.py` + `service.py` only — they own no collection and no schemas; they are read-views over `modules/notes/repository.py`, and the file list should say so.

Layer contract, enforced by review:

- `router.py` — path/query/body binding, dependencies, `response_model`. **Zero Motor calls, zero business rules.**
- `schemas.py` — Pydantic request/response models for this module only.
- `models.py` — Mongo document field constants + `from_document()` mappers.
- `service.py` — business rules, cross-repository orchestration. Raises **domain** exceptions, never `HTTPException`.
- `repository.py` — every Motor query for this module's collection. Returns dicts/models, never raises HTTP.

`app/utils.py`'s DB-touching helpers do **not** go to `shared/` — `authors_by_owner_id` / `derive_author_name` land in `modules/users/repository.py`, `comment_counts` in `modules/comments/repository.py`. Only pure functions belong in `shared/`.

## Phases

Each phase is an independently deployable branch that ends green. Old modules become thin re-export shims mid-migration so `master` is never broken, and are deleted in Phase 4.

### Phase 0 — Safety net (zero source moves)

This is the phase that makes "no new bugs" enforceable rather than aspirational. **Do not start Phase 1 until this is green.**

1. `tests/conftest.py` — app fixture driving the real lifespan, `httpx.AsyncClient(transport=ASGITransport(app))`, a throwaway `DB_NAME` per run, drop-between-tests.
   - **Use a real MongoDB, not `mongomock`.** `notes.py`'s `$lookup` pipeline and `public.py`'s update-with-aggregation-pipeline (`vote_public_note`) are not supported by mocks.
2. `tests/contract/test_routes.py` — assert the exact set of `(method, path, status_code, response_model)` from `app.routes` matches a checked-in frozen list. Any accidental path change fails loudly.
3. `tests/contract/openapi.baseline.json` — capture `GET /openapi.json` from **current** `master`. A test diffs live-vs-baseline. This is the single highest-value safeguard in the plan.
4. Per-module smoke tests written against **today's** code, covering the happy path of all ~25 endpoints plus the documented edge cases that a careless refactor would silently break:
   - login 403 (not 401) on unverified account
   - identical generic message from `resend-verification` / `forgot-password` for existing *and* nonexistent accounts
   - folder cascade delete on `"notes"` leaves `"notes-archive"` untouched
   - unpublished + nonexistent public notes both 404 (never 403)
   - vote delta math: up→down in one call moves both counters; counters clamp at 0
   - upload title collision gets ` (n)` suffix
   - export rejects empty selection with 400
5. `[tool.ruff]` in `pyproject.toml` (target `py311`, line-length matched to existing code so formatting isn't a diff bomb). Only safe fix applied now: delete the dead `normalize_folder_path` import in `routers/tags.py:5`.
6. Re-enable the already-written, commented-out MongoDB service + `uv run pytest` steps in `.github/workflows/deploy_ec2.yaml:27-38`.

**Gate:** suite green against untouched source; baseline committed.

### Phase 1 — `core/` + `db/`

1. `core/config.py` — `Settings(BaseSettings)` with every env var from `.env.example`.
   - **`model_config = SettingsConfigDict(env_file=".env", extra="ignore")`.** `extra="ignore"` is mandatory: `.env` carries `MDSTACK_MCP_TOKEN` / `MDSTACK_EMAIL` / `MDSTACK_PASSWORD` for the MCP container, and pydantic-settings will hard-fail on unknown keys without it.
   - Every default copied **verbatim** from today's `os.getenv` calls, including the malformed `MONGO_URL`.
   - `ADMIN_EMAILS` parsed to a lowercased `set[str]` with the same `split(",")`/`strip()` semantics as `dependencies.py:16`.
   - `get_settings()` with `lru_cache`; modules hold `settings = get_settings()` at import, preserving today's read-once semantics while staying test-overridable.
   - New: `LOG_LEVEL` (default `INFO`). Add to `.env.example`.
2. `core/security.py` ← `app/auth.py`, reading `settings`. Function signatures unchanged.
3. `core/exceptions.py` — `AppError` base with `status_code` / `detail` / `headers`, plus `NotFoundError` (404), `ConflictError` (409), `BadRequestError` (400), `AuthenticationError` (401, sets `WWW-Authenticate: Bearer`), `PermissionDeniedError` (403). One handler registered on the app emitting **exactly** `JSONResponse({"detail": ...}, status_code, headers)` — byte-identical to what `HTTPException` produces today.
4. `core/logging.py` — `configure_logging()` via `dictConfig` with `disable_existing_loggers: False` so uvicorn's own loggers survive.
5. `core/middleware.py` ← `app/middleware.py` verbatim, plus `RequestIdMiddleware` setting `X-Request-ID`. Do **not** add it to CORS `expose_headers` — that would change the CORS contract for no benefit.
6. `db/mongo.py` — connect in lifespan, `close()` on shutdown (today's client is never closed). `db/collections.py` exposes accessor *functions* so they resolve after connect. `db/indexes.py` ← `ensure_indexes()` verbatim.
7. `main.py` → `create_app()` + `lifespan` replacing `@app.on_event("startup")`, still calling `ensure_indexes()`. **Keep `app = create_app()` at module level.**
   - **Middleware order is load-bearing.** Starlette applies outside-in in add order. Register: `CORSMiddleware` → `RequestIdMiddleware` → `RequestCounterMiddleware`, preserving the documented "counter sits inside CORS" property (`main.py:28-31`).
8. `app/auth.py`, `app/middleware.py`, `app/database.py` become re-export shims.
9. Add `pydantic-settings` to `pyproject.toml`. **Then run `uv lock` and commit `uv.lock`** — the Docker build runs `uv sync --frozen`, so editing `pyproject.toml` alone installs nothing (`pyproject.toml:64-70` documents this exact trap).

**Gate:** contract + smoke green.

### Phase 2 — `shared/`

Split `app/utils.py` by purity: pure text/path helpers to `shared/markdown.py` + `shared/paths.py`; `now_iso` out of `models.py` into `shared/datetime.py`; `app/dependencies.py` → `shared/dependencies.py`. Unify the two `oid()` parsers into `shared/objectid.py` — **preserving their different behaviors**: `notes.py` raises 400 "Invalid note id", `public.py` raises 404 "Note not found". Same function, explicit exception parameter; do not collapse them into one status code.

Leave `app/utils.py` / `app/dependencies.py` as shims. **Gate:** green.

### Phase 3 — Modules, one at a time

Dependency order, each step ending with the old `app/routers/<x>.py` deleted, its schemas moved out of `app/models.py`, and `api.py` repointed:

1. `users` (author resolution is needed by nearly everything)
2. `comments`
3. `notes`
4. `folders`
5. `public`
6. `search`, `tags`
7. `upload`, `export`
8. `admin`

**Run the contract + smoke suite after every single module, not at the end of the phase.** Each is its own commit, so a regression bisects to one module.

While moving: services raise the Phase-1 domain exceptions instead of `HTTPException` — but the smoke tests assert the status code and `detail` string are unchanged, so the swap is provably invisible from outside.

`app/models.py` shrinks with each step and is deleted when the last module lands.

### Phase 4 — Teardown

- Delete the shims: `app/auth.py`, `app/database.py`, `app/dependencies.py`, `app/middleware.py`, `app/models.py`, `app/utils.py`, `app/routers/`.
- Delete `_removed/graph.py` and the now-orphaned `GraphNode` / `GraphEdge` / `GraphOut` schemas (already dead — `SKILL.md` "Known open issues").
- Rewrite `backend/SKILL.md`'s "File structure" section to the new layout. It is the project's context doc; a stale one is worse than none.
- Final full OpenAPI diff against the Phase 0 baseline: **must be empty**.
- Confirm `Dockerfile`'s `COPY app ./app` and `pyproject.toml`'s `packages = ["app", "mcp_server"]` still resolve (they do — nothing leaves `app/`).

## Verification

Per phase, and again before merging to `master`:

```bash
cd backend
uv run pytest                       # contract + smoke suite
uv run ruff check app tests
uv run python -c "from app.main import app; print(len(app.routes))"   # Dockerfile's import path
```

End-to-end against a real stack before the `master` push that triggers deploy:

1. `docker compose up -d --build` locally; confirm the container `HEALTHCHECK` on `/api/health` goes healthy.
2. Diff `curl -s localhost:5000/openapi.json` against `tests/contract/openapi.baseline.json` — empty diff.
3. Point the local frontend (`VITE_API_BASE`) at it and walk the flows the suite can't fully cover: register → verify email → login → create/link/publish a note → publish a folder → comment → vote → upload a directory → export a zip → admin dashboard.
4. Exercise the MCP server against the restructured backend (`MDSTACK_API_BASE_URL=http://localhost:5000`, stdio transport) — it is a second independent consumer of the same contract and will catch anything the frontend doesn't touch.
5. Push a non-`master` branch first: CI builds, pushes a branch-tagged image, and now runs the test suite — without triggering the EC2 deploy job.

## Deliberately out of scope (follow-ups, not this work)

- N+1 `count_documents` in `list_public_folders` / `list_my_published_folders` → single `$group` aggregation, mirroring `comment_counts`.
- Pagination on `list_notes` / `list_folders` (currently unbounded). `shared/pagination.py` is intentionally **not** scaffolded here — no endpoint would use it yet, and dead code is not structure.
- Wiring `CORS_ORIGINS` and dropping `allow_origins=["*"]` (which is invalid alongside `allow_credentials=True` per the CORS spec).
- Rotating the committed Mongo Atlas credentials — owner's call, tracked in `SKILL.md`.
- `mypy`. Ruff first; typing after the structure settles, starting with `core/` + `shared/`.
- `mcp_server/` — untouched. It is an HTTP client of this API and imports nothing from `app/`.
