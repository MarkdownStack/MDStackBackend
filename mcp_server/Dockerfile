# syntax=docker/dockerfile:1

# Build context is backend/ (see docker-compose.yml's `mcp` service — build
# context "." with this file as its dockerfile), not mcp_server/ itself,
# because it needs pyproject.toml + uv.lock from the repo root of this
# project to resolve dependencies via uv.
#
# Deliberately does NOT install this project itself (`uv sync
# --no-install-project` in both stages below) — this image only ever runs
# `python -m mcp_server.server` directly off the filesystem, so there's no
# need for hatchling to build/install a "vault-backend" wheel, which would
# also fail here anyway since this image never copies app/ (only
# mcp_server/), and pyproject.toml's [tool.hatch.build.targets.wheel]
# expects both "app" and "mcp_server" packages to exist.
#
# Known trade-off: `uv sync --extra mcp` still installs the base
# [project.dependencies] list too (fastapi, motor, etc.) — pyproject.toml
# doesn't currently separate "core app deps" from "installable standalone"
# groups, so this image carries some weight it doesn't use. Fine at this
# project's scale; split into its own pyproject.toml/lock if that ever
# actually matters.
FROM python:3.11-slim-bookworm AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --extra mcp --no-install-project --no-dev

COPY mcp_server ./mcp_server

FROM python:3.11-slim-bookworm AS runtime

RUN useradd --create-home --uid 1000 --shell /usr/sbin/nologin appuser

WORKDIR /app

COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv
COPY --from=builder --chown=appuser:appuser /app/mcp_server ./mcp_server

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# All MDSTACK_* vars (API base URL, transport, host/port/path, the bearer
# token, and whichever of ACCESS_TOKEN vs EMAIL+PASSWORD you use to
# auto-login) are intentionally NOT set here — same reasoning as
# backend/Dockerfile: provide them via compose's env_file/environment,
# never bake real values into the image.
USER appuser

EXPOSE 8090

# A bare TCP connect rather than an HTTP request: the Streamable HTTP
# endpoint expects real MCP protocol framing on every request (session
# headers, JSON-RPC body), so a plain GET would just bounce off it with a
# 4xx that doesn't actually tell you whether the process is healthy — this
# only confirms the port is open and accepting connections, which is enough
# to catch "process crashed on startup".
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import socket; socket.create_connection(('localhost', 8090), timeout=3)" || exit 1

CMD ["python", "-m", "mcp_server.server"]
