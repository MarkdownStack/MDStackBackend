"""Postgres engine/session lifecycle — replaces db/mongo.py.

Mirrors the shape db/mongo.py had (a module-level client created eagerly at
import, a close()/dispose() wired into the app's lifespan) so main.py's
startup/shutdown story doesn't change, only what it's connecting to.

`get_db()` is a FastAPI dependency yielding one `AsyncSession` per request
(commits on clean exit, rolls back on exception) — every repository
function in app/modules/*/repository.py takes a `session: AsyncSession` as
its first argument instead of reaching for a module-level collection
global the way the Motor code did, since SQLAlchemy sessions are NOT
safe to share across concurrent requests the way Motor's collection
handles were.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from ..core.config import get_settings

settings = get_settings()


class Base(DeclarativeBase):
    """Shared declarative base for every ORM model in db/models.py."""


# echo=False in production; flip via Settings.log_level == "DEBUG" below so a
# noisy SQL log is opt-in, not a surprise in prod. database_url is a plain,
# direct Postgres connection in both environments — local Docker, and a
# managed instance (e.g. AWS RDS) in production — so asyncpg needs no
# special-casing here, unlike it would behind a transaction-mode connection
# pooler (e.g. PgBouncer in transaction mode), which needs its prepared-
# statement cache disabled and SSL forced on to work correctly.
engine = create_async_engine(
    settings.database_url,
    echo=settings.log_level.upper() == "DEBUG",
    pool_pre_ping=True,
)

# expire_on_commit=False: a repository function typically returns the ORM
# object it just wrote (mirroring the Motor code's "insert, then hand back
# the dict"), and the caller (service.py) reads its columns *after* the
# session's own commit — without this, SQLAlchemy would re-fetch every
# attribute lazily post-commit, which needs an *open* session/connection
# that request scope may no longer have.
async_session_factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: one session per request, committed on success,
    rolled back on any exception raised while handling the request."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def session_scope() -> AsyncGenerator[AsyncSession, None]:
    """Same commit/rollback contract as get_db(), for the handful of
    call sites that aren't FastAPI request handlers and can't use
    Depends(get_db) — e.g. core/middleware.py's RequestCounterMiddleware,
    which runs via asyncio.create_task, outside any request's own
    dependency-injected session."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """Create every table declared in db/models.py if it doesn't already
    exist — the Postgres equivalent of db/indexes.py's ensure_indexes(),
    called once from the app's lifespan startup (see app/main.py).

    This is intentionally the same "declare it in code, apply it at
    startup" spirit as the Mongo version rather than a full migration
    tool: good enough for a single-owner personal vault. A real multi-
    environment rollout should graduate to the Alembic revisions in
    backend/alembic/ instead (see POSTGRES_MIGRATION.md) — create_all()
    only ever adds tables/indexes that don't exist yet, it never alters an
    existing one, so it's safe to leave running alongside Alembic too.
    """
    from . import models  # noqa: F401  (registers every table on Base.metadata)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close() -> None:
    """Disposes the connection pool — called from the app's lifespan on
    shutdown, same timing db/mongo.py's close() had."""
    await engine.dispose()
