# syntax=docker/dockerfile:1

# =============================================================================
# Builder stage — installs dependencies with uv (this project's package
# manager, per pyproject.toml + uv.lock) into a self-contained virtualenv.
# Nothing from this stage except the finished .venv and the app code makes
# it into the final image, so build tools and package caches never bloat
# the runtime image.
# =============================================================================
FROM python:3.11-slim-bookworm AS builder

# bcrypt / pydantic-core ship prebuilt wheels for common platforms, but keep
# a compiler around in the builder in case a wheel isn't available for the
# host's target architecture. Discarded before the final stage regardless.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Grab uv itself from its official image rather than `pip install uv` — no
# network round trip to PyPI just to bootstrap the tool that installs
# everything else.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app

# Dependencies first, application code second — as long as pyproject.toml /
# uv.lock haven't changed, Docker reuses this (slow, network-bound) layer on
# every rebuild instead of reinstalling everything just because a .py file
# changed.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

COPY app ./app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# =============================================================================
# Runtime stage — slim, no compiler, no uv, no dev/test dependencies
# (pytest etc. from [dependency-groups.dev] are excluded via --no-dev
# above), runs as a non-root user.
# =============================================================================
FROM python:3.11-slim-bookworm AS runtime

RUN useradd --create-home --uid 1000 --shell /usr/sbin/nologin appuser

WORKDIR /app

COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv
COPY --from=builder --chown=appuser:appuser /app/app ./app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# MONGO_URL, DB_NAME, CORS_ORIGINS, JWT_SECRET_KEY, JWT_ALGORITHM,
# ACCESS_TOKEN_EXPIRE_MINUTES are intentionally NOT set here — provide them
# at `docker run -e ...`, a compose env_file, or your orchestrator's own
# secrets mechanism. Never bake real credentials into the image itself; see
# .env.example for the full list this app reads at startup.
USER appuser

EXPOSE 8000

# Hits the app's own /api/health route (see app/main.py) using Python's
# stdlib instead of curl, so the runtime image doesn't need curl installed
# just for this one check.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
