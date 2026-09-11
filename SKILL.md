---
name: markdownstack-backend-context
description: Architecture, routers, auth/email flows, admin stats pipeline, MCP server, and deployment for MarkdownStack's backend (FastAPI + MongoDB, at /Users/parimal/Projects/obsidian-clone/backend). Read this before touching anything under backend/ — see the repo root's SKILL.md first for what the product is overall.
---

# MarkdownStack backend — context

FastAPI + MongoDB (via Motor, the async driver), JWT bearer auth, managed with `uv` (`pyproject.toml` + `uv.lock` — not `pip`/`requirements.txt`). One router per resource under `app/routers/`. Deployed as a Docker image; see **Deployment** below.

## File structure

- `app/main.py` — FastAPI app: CORS (`expose_headers=["Content-Disposition"]` so the frontend can read a download's real filename cross-origin), the request-counting middleware (see **Admin dashboard** below), includes every router, runs `ensure_indexes()` on startup.
- `app/routers/`:
  - `auth.py` — register/login/me, email verification, resend-verification, forgot/reset password. See **Accounts, auth, and email** below.
  - `admin.py` — `GET /api/admin/stats`, gated by `get_current_admin`. See **Admin dashboard** below.
  - `notes.py` — private CRUD + `/published/mine`.
  - `folders.py` — CRUD, and a **recursive cascade delete**: deleting a folder deletes it, every note inside it, every subfolder, and every note inside those subfolders (confirmed client-side first).
  - `search.py` — Mongo `$text` index search.
  - `tags.py` — tag listing / notes-by-tag.
  - `upload.py` — bulk folder/file import (multipart, preserves relative paths).
  - `public.py` — everything unauthenticated *except* posting a comment: reading published notes/comments and voting need no login.
  - `export.py` — bundles selected folders (or the whole vault) into a streamed `.zip` download.
- `app/models.py` — every Pydantic request/response model. `now_iso()` (UTC ISO-8601 timestamp helper) lives here too, imported by most routers.
- `app/database.py` — Motor client/db handle, every collection reference, and `ensure_indexes()` (the only place indexes are declared — read it before adding a new query pattern to see if it needs one).
- `app/dependencies.py` — `get_current_user` (required auth, JWT-only, no DB round trip on the hot path — see its own docstring for why), `get_current_user_optional` (same but returns `None` instead of 401, used by the Explore feed so it can personalize for logged-in callers while staying open to anonymous ones), `get_current_admin` (see **Admin dashboard**), `ADMIN_EMAILS`/`is_admin_email`.
- `app/auth.py` — password hashing (bcrypt), JWT encode/decode (`create_access_token`/`decode_access_token`).
- `app/email.py` — Mailgun client. See **Accounts, auth, and email** below.
- `app/middleware.py` — `RequestCounterMiddleware`. See **Admin dashboard** below.
- `app/utils.py` — shared helpers: `extract_tags`/`extract_links` (regex-based, run server-side on every note save), `excerpt` (plain-text preview for cards), `normalize_folder_path`, and `derive_author_name`/`authors_by_owner_id`/`comment_counts` (shared between `public.py` and `notes.py` so every published-notes feed resolves author names/comment counts identically).
- `mcp_server/` — a separate MCP server; see its own section below.

## Data model (Mongo collections, `app/database.py`)

- **`users`** — `email` (unique index), `username` (sparse-unique — old accounts predating the username field have none), `password_hash`, `is_verified`, `verification_token`/`verification_token_expires` (sparse-unique, `$unset` once verified), `password_reset_token`/`password_reset_token_expires` (sparse-unique, same pattern), `created_at`/`updated_at`. No `is_admin` field — admin status is computed at read time from `ADMIN_EMAILS`, not stored (see below).
- **`notes`** — scoped by `owner_id`; `title` unique per owner, full-text index on `title`+`content`, indexes on `folder_path`/`tags`/`links`/`is_public`+`upvotes`. `upvotes`/`downvotes` are anonymous and client-tracked via localStorage — no server-side vote-ownership (a documented "temperature, not a tamper-proof number" tradeoff). `created_at`/`updated_at` both round-trip to the frontend and are shown together in the note editor's title block.
- **`folders`** — scoped by `owner_id`; unique on `(owner_id, path)`, indexed on `(owner_id, is_public)` for the published-folders feed.
- **`comments`** — `note_id`+`created_at` and `note_id`+`upvotes` indexes (chronological list, and a future "top comments" sort). Author is always resolved from the real account — no free-typed names, no anonymous spoofing.
- **`request_stats`** — one doc per UTC calendar day, `_id` is the `"YYYY-MM-DD"` string itself (no separate index needed). Written only by `RequestCounterMiddleware`, read only by `GET /api/admin/stats`. See **Admin dashboard**.

## Accounts, auth, and email

Registration takes `username` + `email` + `password` (`USERNAME_PATTERN = r"^[a-zA-Z0-9_]{3,24}$"`, both stored lowercased for case-insensitive uniqueness). **Login accepts either** — `_find_by_identifier(identifier)` in `routers/auth.py` queries `{"$or": [{"email": identifier}, {"username": identifier}]}`, and every recovery flow (resend-verification, forgot-password) takes the same `identifier` field for the same reason.

**Email verification is mandatory**: `POST /api/auth/login` returns 403 ("Please verify your email before logging in.") until `is_verified` is true. Registering sends a verification email (best-effort — a Mailgun failure doesn't fail the registration itself); `GET /api/auth/verify-email?token=` flips the flag. Tokens are `secrets.token_urlsafe(32)`, 24h TTL (`VERIFICATION_TOKEN_TTL`). `POST /api/auth/resend-verification` and `POST /api/auth/forgot-password` both **always return the same generic `{message}`** regardless of whether the account exists or is already verified — a deliberate enumeration-prevention pattern, don't "fix" it to be more specific.

**Forgot/reset password** mirrors verification: `POST /api/auth/forgot-password` (generic response, 1h TTL — deliberately shorter than verification's 24h, since a reset link grants "set this account's password" outright with no old password needed) → emailed link → `POST /api/auth/reset-password` (token + new password) → `password_hash` updated, token fields `$unset`.

**`app/email.py`** is a thin Mailgun HTTP client (`httpx.AsyncClient`, `auth=("api", MAILGUN_API_KEY)`), reading `MAILGUN_URI` (the full `.../messages` endpoint), `MAILGUN_API_KEY`, `MAILGUN_FROM_ADDR`, and `FRONTEND_BASE_URL` (used to build the `/verify-email?token=`/`/reset-password?token=` links — **must** be set to the real frontend origin before a real deploy, or emailed links point at `localhost:5173`). Both `send_verification_email`/`send_password_reset_email` are best-effort: they return `True`/`False` and never raise, so a Mailgun outage degrades to "no email sent" rather than breaking registration/reset requests outright. **Gotcha already hit once**: these env vars are read at **import time** (module-level `os.getenv(...)`), so editing `.env` while a `uvicorn` process is already running does nothing until it's restarted — also check the process's cwd, since `load_dotenv()` resolves relative to it.

## Admin dashboard

Gated by `ADMIN_EMAILS` (comma-separated env var, e.g. `ADMIN_EMAILS=you@example.com,other@x.com`) — a config change, not a database write. `is_admin_email(email)` in `dependencies.py` is the single source of truth, used both by `get_current_admin` (the dependency actually gating `/api/admin/*`, which does one extra DB round trip to fetch the caller's email — acceptable since admin endpoints are low-traffic) and by `routers/auth.py`'s `_user_out` (which surfaces it as `UserOut.is_admin`, purely so the frontend can show/hide admin UI without guessing — the endpoint itself still re-checks server-side regardless of what the frontend sends).

`RequestCounterMiddleware` (`app/middleware.py`) increments a per-UTC-day counter in `request_stats` on every real request, via `asyncio.create_task` (**not** awaited — never adds latency to the request it's counting) with the Mongo write wrapped in a bare `try/except` (a stats-recording failure must never break a real request). Skips `OPTIONS` preflights, `/api/health`, and `/api/admin/*` itself (so checking the dashboard doesn't inflate the number you're looking at).

`GET /api/admin/stats` (`routers/admin.py`) returns: `total_requests` (sums every daily doc — cheap enough at this scale that a separate running counter isn't worth the extra write contention), `requests_today`, `requests_last_7_days` (a small per-day list), plus `total_users`/`total_notes`/`total_published_notes` since they were cheap to add alongside.

## Publishing, comments, and upvotes

A note's `is_public` toggle (and the equivalent for whole folders) makes it reachable without login. Comment posting requires an account (resolved author — no anonymous spoofing); reading and voting stay open to everyone. Three related-but-different feeds all exist: the anonymous public feed (`public.py`), the logged-in "Explore" feed (excludes your own notes, via `get_current_user_optional`), and "My Published Notes" (only your own). All three resolve author names/comment counts through the same `utils.py` helpers so they never drift out of sync with each other.

## Export

`export.py` bundles a hand-picked subset of folders (or the whole vault) into a streamed `.zip`, driven by the frontend's hierarchical folder-selection tree.

## MCP server (`backend/mcp_server/`)

A separate concern from the FastAPI app above: exposes the backend as ~22 tools for an MCP client (Claude Desktop, Claude Code, Claude.ai), covering auth, notes CRUD + publishing, folders (incl. cascading delete), search/tags, the public Explore feed + voting + comments, and vault export. Built as a plain `httpx` client of the *running* FastAPI backend (`mcp_server/client.py`), not a second copy of the business logic talking to MongoDB directly — every write still goes through the routers' own validation. Not covered: `/api/upload` (its multipart/`webkitRelativePath` shape doesn't map cleanly onto a tool call).

- Built on the standalone `fastmcp` package (pinned `fastmcp>=3.0,<4` — a prior `>=2.0,<3` pin silently resolved to an old `2.2.0` that lacked the `host`/`port` calling style `server.py` uses; see `mcp_server/README.md`'s "Which FastMCP?" section for the full `uv.lock` re-resolution story). `server.py` has a try/except import so it works both as a package (`python -m mcp_server.server`) and as a standalone script (`fastmcp run`/`dev`/`install`).
- **Two transports**: `MDSTACK_MCP_TRANSPORT` unset runs stdio (a local subprocess Claude Desktop spawns directly — local dev/testing). Set to `http` and it runs as a persistent Streamable HTTP service instead — what makes remote hosting possible.
- **Remote deployment**: an `mcp` service in `backend/docker-compose.yml`, on the same `app-network` as `backend`/`nginx`, talking to `backend` over Docker's internal DNS (not `localhost`). Built locally on the EC2 box via `build:` (unlike `backend`, which pulls a published image) — there's no CI job publishing an `mdstack_mcp` image yet. Exposed through nginx at `/mcp` on the existing domain/cert, with the three proxy settings Streamable HTTP needs that plain REST doesn't: `proxy_buffering off`, empty `Connection` header, long read/send timeouts.
- **Auth**: a single shared bearer token (`MDSTACK_MCP_TOKEN`, checked via `fastmcp.server.auth.providers.jwt.StaticTokenVerifier`) gates the whole `/mcp` path — a single-shared-secret model appropriate for "exactly one trusted caller," not multi-tenant OAuth.
- **Status, still unresolved**: `fastmcp` resolves to `3.4.0`, EC2 is redeployed on it, `curl https://api.stalk-my-money.in/mcp` correctly returns a JSON-RPC error (proof nginx → container routing works). Adding it as a remote connector in Claude Desktop still fails with "Couldn't reach MarkdownStack" even with a manual `Authorization: Bearer <token>` header — next step is comparing a real `POST .../mcp` against MCP's actual initialize handshake (`Accept: application/json, text/event-stream`) against `docker compose logs mcp`/`nginx` at the moment Claude attempts to connect, not just a bare `curl -i GET`.

## Deployment

- **CI/CD**: `.github/workflows/deploy_ec2.yaml` — on push to any branch, builds and pushes a Docker image (`parimalmahindrakar/mdstack_backend:<branch>_<short-sha>`) to Docker Hub; on `master` specifically, also tags/pushes `:latest` and SSHes into the EC2 box to redeploy via `docker-compose.yml` (backend + nginx + mcp services).
- **Dockerfile**: multi-stage — a `uv`-based builder stage with a compiler for native deps (bcrypt, pydantic-core), a clean non-root runtime stage with just the finished venv.
- Tests are stubbed out in the CI workflow (commented-out MongoDB service + `uv run pytest` steps) — there's no test suite yet, not just a disabled one.

## Env vars (`.env.example` is the reference)

`MONGO_URL`, `DB_NAME`, `CORS_ORIGINS` (**dead config** — `main.py` hardcodes `origins = ["*"]` and never reads this var; either wire it up or drop it from `.env.example`, don't assume it does anything today), `JWT_SECRET_KEY`, `JWT_ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `MAILGUN_URI`/`MAILGUN_API_KEY`/`MAILGUN_FROM_ADDR`/`FRONTEND_BASE_URL` (see **Accounts, auth, and email**), `ADMIN_EMAILS` (see **Admin dashboard**), `MDSTACK_MCP_TOKEN` (see **MCP server**).

## Known open issues

- **Security, high priority**: see the repo root `SKILL.md` — the live Mongo Atlas password in `.env.example`/`database.py`'s fallback. Don't remove the warning; owner rotates it on a call.
- **`CORS_ORIGINS` is unused** — see **Env vars** above.
- **Dead code**: `_removed/graph.py` — the old graph-view backend endpoint, disconnected from `main.py` (the frontend's graph view was removed too; not a live bug, just unused).
- **MCP server**: no CI job builds/pushes an `mdstack_mcp` image yet (rebuilt from source on the EC2 box itself every deploy); the `mcp` container also currently pulls in the full base app dependency list (fastapi, motor, etc.) it never uses, since `pyproject.toml` doesn't separate "core app" deps from the `mcp` extra's own — harmless at this scale, would need its own `pyproject.toml`/lock to actually fix. The Claude Desktop remote-connector handshake failure above is still open.
- **This session added, not yet stress-tested**: the request-counter middleware's `asyncio.create_task` fire-and-forget write has no backpressure — under a genuine traffic spike this could queue up a large number of pending Mongo writes; fine at this project's real-world scale, worth revisiting if traffic ever grows meaningfully.
