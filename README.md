# MarkdownStack — Backend

FastAPI API for the MarkdownStack vault: auth, notes, folders, search, tags, uploads, and the public/publish feature. Persistence is PostgreSQL 16 via SQLAlchemy 2.0's async ORM + asyncpg (migrated off MongoDB — see `POSTGRES_MIGRATION.md` for the migration itself and `scripts/migrate_mongo_to_postgres.py` for the one-time data-import script).

Two ways to run it are documented below — pick whichever fits: **Docker** (no local Python setup needed) or **traditional** (runs directly on your machine via `uv`, with a plain `pip`/`venv` fallback).

## Architecture

### System overview

```mermaid
flowchart TB
    subgraph CLIENT["Browser — React 18 + Vite SPA"]
        UI["VaultShell / Sidebar / NoteEditor"]
        CTX["Context layer<br/>Auth · Settings · Sync · Theme · ..."]
        IDB[("IndexedDB<br/>mdstack_vault_&lt;userId&gt;<br/>notesSummary · notesFull · folders · pendingWrites")]
        SYNCENGINE["syncEngine.js<br/>background retry queue"]
        AX["axios client<br/>JWT bearer header"]

        UI --> CTX
        UI -- "cache-first read/write" --> IDB
        SYNCENGINE -- "read/write queue" --> IDB
        SYNCENGINE -- "flush on debounce / online / interval" --> AX
        UI -- "list / get / create / update / delete" --> AX
    end

    S3["S3 static hosting<br/>deploy_on_s3.yaml"]
    CLIENT -. "static build served from" .-> S3

    AX == "HTTPS + JWT" ==> NGINX

    subgraph SERVER["EC2 — docker-compose"]
        NGINX["nginx<br/>reverse proxy"]
        ROUTER["FastAPI routers<br/>users · notes · folders · public<br/>comments · search · tags · upload · export · admin"]
        SVC["service.py<br/>business logic"]
        REPO["repository.py<br/>SQLAlchemy async queries"]
        MCP["mcp_server<br/>fastmcp, HTTP client of backend"]

        NGINX --> ROUTER
        NGINX -- "/mcp" --> MCP
        MCP -- "plain HTTPS" --> NGINX
        ROUTER --> SVC --> REPO
    end

    REPO == "asyncpg" ==> PG[("PostgreSQL 16<br/>users · user_preferences · folders<br/>notes · tags · note_tags · comments · request_stats")]

    SVC -. "best-effort email" .-> MAILGUN["Mailgun API"]

    MONGO[("MongoDB Atlas<br/>retired — pre-migration")]
    MONGO -. "one-off script<br/>migrate_mongo_to_postgres.py" .-> PG
```

### Entity relationships

```mermaid
erDiagram
    USER ||--|| USER_PREFERENCES : has
    USER ||--o{ FOLDER : owns
    USER ||--o{ NOTE : owns
    USER ||--o{ TAG : owns
    USER ||--o{ COMMENT : writes
    FOLDER ||--o{ NOTE : "contains (nullable)"
    NOTE }o--o{ TAG : "tagged via note_tags"
    NOTE ||--o{ COMMENT : has

    USER {
        uuid id PK
        string email UK
        string username UK
        string password_hash
        bool is_verified
        datetime created_at
        datetime updated_at
    }
    USER_PREFERENCES {
        uuid user_id PK,FK
        string theme
        int autosave_interval_ms
        jsonb extra
    }
    FOLDER {
        uuid id PK
        uuid owner_id FK
        text path
        bool is_public
    }
    NOTE {
        uuid id PK
        uuid owner_id FK
        uuid folder_id FK
        text folder_path
        text title
        text content
        bool is_public
        int upvotes
        int downvotes
    }
    TAG {
        uuid id PK
        uuid owner_id FK
        string name
    }
    COMMENT {
        uuid id PK
        uuid note_id FK
        uuid owner_id FK
        text content
        int upvotes
    }
    REQUEST_STAT {
        string date PK
        int count
        jsonb methods
    }
```

### Offline-first sync sequence

How the frontend's IndexedDB cache and background sync queue (`frontend/src/lib/offlineDb.js`, `frontend/src/lib/syncEngine.js`) interact with this API when a note is opened, edited, and eventually synced:

```mermaid
sequenceDiagram
    actor U as User
    participant UI as NoteEditor (React)
    participant IDB as IndexedDB
    participant SYNC as syncEngine.js
    participant API as FastAPI backend
    participant PG as Postgres

    Note over U,PG: Opening a note (cache-first)
    U->>UI: opens note
    UI->>IDB: getCachedNote(id) / getPendingWrite(id)
    IDB-->>UI: cached note (if any)
    UI-->>U: renders instantly from cache
    UI->>API: GET /api/notes/{id}
    API->>PG: SELECT note
    PG-->>API: row
    API-->>UI: fresh NoteOut
    alt no pending local edit
        UI->>IDB: putCachedNote(fresh, _dirty=false)
        UI-->>U: re-renders with server copy
    else pending edit still queued
        UI-->>UI: keep local (newer) content on screen
    end

    Note over U,PG: Typing (debounced autosave)
    U->>UI: types in editor
    UI->>UI: scheduleSave() resets debounce timer
    Note right of UI: after autosaveInterval of inactivity
    UI->>IDB: putCachedNote(content, title, _dirty=true)

    alt online
        UI->>API: PUT /api/notes/{id}
        API->>PG: UPDATE note
        PG-->>API: updated row
        API-->>UI: 200 OK
        UI->>IDB: putCachedNote(updated, _dirty=false)
        UI-->>U: "Saved"
    else offline / request fails
        UI->>SYNC: queueNoteUpdate(id, payload)
        SYNC->>IDB: putPendingWrite(id, payload)
        UI-->>U: "Saved offline — will sync"
    end

    Note over U,PG: Background sync (later, connection restored)
    SYNC->>SYNC: 'online' event / 30s interval tick
    SYNC->>IDB: getAllPendingWrites()
    IDB-->>SYNC: queued rows
    loop each queued write
        SYNC->>API: PUT /api/notes/{id}
        alt success
            API->>PG: UPDATE note
            PG-->>API: updated row
            API-->>SYNC: 200 OK
            SYNC->>IDB: deletePendingWrite(id) + putCachedNote(_dirty=false)
        else still offline
            SYNC->>SYNC: backoff, retry later
        end
    end
    SYNC-->>UI: status update (pendingCount, isOnline)
    UI-->>U: indicator flips back to "Saved"
```

## Prerequisites

- A reachable Postgres 16 instance — a local Docker container for dev (see Option C below), a managed Postgres instance for production (this project uses **AWS RDS**)
- Either **Docker** (Docker way), or **Python 3.11+** (traditional way)

## Environment variables

Copy the example file and fill in your own values — never commit a real `.env`:

```bash
cp .env.example .env
```

| Variable | Default (in code) | Notes |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://mdstack:mdstack@localhost:5432/mdstack` | Full SQLAlchemy async URL — what the running app (and Alembic) connects with (see `app/db/postgres.py`, `alembic/env.py`). The default matches the local Docker Postgres from Option C. In production this is a plain, direct connection to a managed Postgres instance (AWS RDS) — same `postgresql+asyncpg://` shape as the local default, just with that instance's own host/user/password/database. See `.env.example`'s "Production" section. |
| `CORS_ORIGINS` | — | Present in `.env.example` for documentation, but `app/main.py` currently hardcodes `allow_origins=["*"]` — this variable isn't actually read yet. Don't rely on it to restrict origins. |
| `JWT_SECRET_KEY` | — | Set this to a long random string. Required for signing auth tokens. |
| `JWT_ALGORITHM` | `HS256` | |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `10080` (7 days) | |

> **Security note:** `backend/.env.example` still carries a real, live MongoDB Atlas password committed in plaintext from before the Postgres migration (in a commented-out block). This is a known issue the project owner is aware of and will rotate on a call — leave the warning comments around it in place.

> **Heads up:** the sections immediately below (Options A and B) still describe the pre-Postgres, MongoDB-based setup and haven't been updated yet — the env vars and commands they show (`MONGO_URL`, `docker run ... mongo:7`, etc.) are stale. **Option C** below is current and is the supported way to run this locally (Docker) or point it at production (AWS RDS).

---

## Option A — Docker

The backend ships a multi-stage `Dockerfile` (uv-based builder → slim non-root runtime image) and a `.dockerignore`. There's no `docker-compose.yml` in the repo yet, so either run Mongo and the API as two separate containers, or point at an existing Mongo instance (e.g. Atlas).

1. **Start MongoDB** (skip if you're pointing at Atlas or an already-running instance):
   ```bash
   docker run -d --name vault-mongo -p 27017:27017 mongo:7
   ```

2. **Build the backend image** (from the `backend/` directory):
   ```bash
   cd backend
   docker build -t markdownstack-backend .
   ```

3. **Run it**, passing env vars explicitly (the image intentionally has none baked in — see the comment in the `Dockerfile`):
   ```bash
   docker run -d \
     --name markdownstack-backend \
     -p 5000:5000 \
     -e MONGO_URL="mongodb://host.docker.internal:27017" \
     -e DB_NAME="vault" \
     -e JWT_SECRET_KEY="change-this-to-a-long-random-string" \
     -e JWT_ALGORITHM="HS256" \
     -e ACCESS_TOKEN_EXPIRE_MINUTES="10080" \
     markdownstack-backend
   ```
   - Use `host.docker.internal` (Mac/Windows) to reach a Mongo container/process running on your host from inside the backend container. On Linux, use `--network host` or the Mongo container's name on a shared Docker network instead.
   - Or use an `--env-file .env` flag instead of individual `-e` flags, once you've filled in `.env` from `.env.example`.

4. **Verify it's up**:
   ```bash
   curl http://localhost:5000/api/health
   # {"status":"ok"}
   ```
   The image also has a built-in `HEALTHCHECK` hitting the same endpoint every 30s, so `docker ps` will show `(healthy)`/`(unhealthy)` once it settles.

5. API docs: http://localhost:5000/docs

To rebuild after code changes: `docker build -t markdownstack-backend .` again (the Dockerfile's layer order means dependency installs are cached and only your app code re-copies, so rebuilds are fast).

---

## Option B — Traditional (run directly on your machine)

### B1. With `uv` (recommended — this is what the project is actually set up for)

[`uv`](https://docs.astral.sh/uv/) manages the virtualenv for you from `pyproject.toml` / `uv.lock` — no manual `venv` needed.

Install `uv` if you don't have it:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh   # macOS/Linux
# see https://docs.astral.sh/uv/getting-started/installation/ for Windows
```

Then:
```bash
cd backend
cp .env.example .env        # fill in MONGO_URL / JWT_SECRET_KEY etc.
uv sync                     # installs the exact locked dependencies into .venv
uv run uvicorn app.main:app --reload --port 5000
```

API docs: http://localhost:5000/docs

Useful `uv` commands:
```bash
uv sync                     # install/update deps to match uv.lock
uv add <package>            # add a new dependency (updates pyproject.toml + uv.lock)
uv run <command>            # run any command inside the project's venv, e.g. uv run pytest
```

### B2. With plain `pip` + `venv` (no `uv`)

There's no `requirements.txt` in the repo (dependencies are tracked in `pyproject.toml`/`uv.lock`), but you can install straight from `pyproject.toml` with pip:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e .
cp .env.example .env             # fill in MONGO_URL / JWT_SECRET_KEY etc.
uvicorn app.main:app --reload --port 5000
```

Note this won't pin the exact versions in `uv.lock` — it resolves against the version ranges in `pyproject.toml` instead. Prefer `uv` (B1) if you want a reproducible install.

---

## Option C — docker-compose (API + nginx; Postgres in Docker locally, AWS RDS in production)

`backend/docker-compose.yml` wires up this API (as `backend`), the MCP server (as `mcp`), and the reverse proxy in `nginx/` on a shared `app-network`, matching what `nginx.conf`'s upstream (`backend:5000`) expects. It does **not** define a Postgres service anymore — `backend`'s `DATABASE_URL` is read straight from `./.env`, and what you put there depends on which of the two setups below you're running:

- **Local dev**: `docker-compose.override.yml` (git-ignored-in-spirit, dev-only, never deployed) adds a `postgres` service back in and points `backend`'s `DATABASE_URL` at it automatically when both files are present — which they are by default, since Compose merges an `docker-compose.override.yml` next to `docker-compose.yml` without you asking for it. It also publishes Postgres on `localhost:5432` so `uv run alembic` / a local `psql` can reach it even if you're running the backend itself outside Docker.
- **Production**: only `docker-compose.yml` is deployed (see below) — no local Postgres container exists at all. Set `DATABASE_URL` in the EC2 box's `./.env` to your RDS instance's connection string instead — a plain, direct Postgres connection (`.env.example`'s "Production" section has the exact format).

From the `backend/` directory, for local dev:
```bash
cd backend
cp .env.example .env   # local default DATABASE_URL is already correct — fill in JWT_SECRET_KEY etc.
docker compose up --build -d
```

This builds the API and nginx images locally from their Dockerfiles, plus pulls `postgres:16-alpine` for the local-only Postgres container the override file adds. The API isn't published to the host directly (nginx is the only public entrypoint on 80/443) — uncomment the `ports:` block under `backend` in `docker-compose.yml` if you want to hit port 5000 directly while debugging. (Postgres itself is already published to `localhost:5432` by the override file.)

```bash
docker compose logs -f backend   # tail one service's logs
docker compose down              # stop everything (add -v to also drop the local pgdata volume)
```

### Production deploys (CI/CD)

`.github/workflows/deploy_ec2.yaml` builds and pushes `parimalmahindrakar/mdstack_backend` to Docker Hub on every push to `master`, then SSHes into the EC2 host and runs `git pull` + `docker compose pull backend` + `docker compose build nginx` + `docker compose up -d` there. That means:
- The production `backend/docker-compose.yml` on EC2 pulls the pre-built image (`image: parimalmahindrakar/mdstack_backend:latest`) instead of building it — the EC2 box never runs a heavy Docker build for the API, which is what filled its disk before.
- `nginx` still builds locally on the EC2 box from `nginx/` (small, cheap build) — its image isn't published to Docker Hub yet.
- The deploy workflow only ever copies `docker-compose.yml` itself, never `docker-compose.override.yml` — so production always runs the RDS-backed setup above, never the local Postgres container, even though both files live in the same repo.
- The EC2 deploy directory needs to be an actual git clone of this repo so `git pull` picks up changes to `docker-compose.yml`/`nginx/`, not just new backend code.
- `./.env` on the EC2 box itself is not part of the repo and isn't touched by `git pull` — its `DATABASE_URL` (the RDS connection string) is set once, by hand, on that box.

---

## Project layout

```
app/
  main.py          FastAPI app, CORS, router registration, /api/health
  database.py      Motor client, collections, index setup
  auth.py          password hashing / JWT helpers
  dependencies.py  get_current_user / get_current_user_optional
  models.py        Pydantic models
  utils.py         tag/link extraction, excerpts, author resolution
  routers/         one router per resource (auth, notes, folders, search, tags, upload, public)
```

## Tests

`pytest` is available as a dev dependency (`uv sync` installs it; omit `--no-dev` if you're replicating the Docker build's dependency step manually). No test suite exists in the repo yet — `uv run pytest` once you've added some.
