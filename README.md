# MarkdownStack — Backend

FastAPI + MongoDB (Motor async driver) API for the MarkdownStack vault: auth, notes, folders, search, tags, uploads, and the public/publish feature.

Two ways to run it are documented below — pick whichever fits: **Docker** (no local Python setup needed) or **traditional** (runs directly on your machine via `uv`, with a plain `pip`/`venv` fallback).

## Prerequisites

- A reachable MongoDB instance (local, Docker, or Atlas)
- Either **Docker** (Docker way), or **Python 3.11+** (traditional way)

## Environment variables

Copy the example file and fill in your own values — never commit a real `.env`:

```bash
cp .env.example .env
```

| Variable | Default (in code) | Notes |
|---|---|---|
| `MONGO_URL` | — | Your MongoDB connection string. |
| `DB_NAME` | `vault` | Database name. |
| `CORS_ORIGINS` | — | Present in `.env.example` for documentation, but `app/main.py` currently hardcodes `allow_origins=["*"]` — this variable isn't actually read yet. Don't rely on it to restrict origins. |
| `JWT_SECRET_KEY` | — | Set this to a long random string. Required for signing auth tokens. |
| `JWT_ALGORITHM` | `HS256` | |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `10080` (7 days) | |

> **Security note:** `backend/.env.example` and the fallback default in `backend/app/database.py` currently contain a real, live MongoDB Atlas password committed in plaintext. This is a known issue the project owner is aware of and will rotate on a call — always set your own `MONGO_URL` in `.env` rather than relying on the fallback, and don't remove the warning comments around it.

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
     -p 8000:8000 \
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
   curl http://localhost:8000/api/health
   # {"status":"ok"}
   ```
   The image also has a built-in `HEALTHCHECK` hitting the same endpoint every 30s, so `docker ps` will show `(healthy)`/`(unhealthy)` once it settles.

5. API docs: http://localhost:8000/docs

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
uv run uvicorn app.main:app --reload --port 8000
```

API docs: http://localhost:8000/docs

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
uvicorn app.main:app --reload --port 8000
```

Note this won't pin the exact versions in `uv.lock` — it resolves against the version ranges in `pyproject.toml` instead. Prefer `uv` (B1) if you want a reproducible install.

---

## Running MongoDB locally (for either option)

```bash
docker run -d --name vault-mongo -p 27017:27017 mongo:7
```
or install MongoDB Community Server locally and start it. Either way, point `MONGO_URL` at it (e.g. `mongodb://localhost:27017` when running the backend outside Docker, or `mongodb://host.docker.internal:27017` when the backend itself is in a container).

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
