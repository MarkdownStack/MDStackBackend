from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import api_router
from .core.config import get_settings
from .core.exceptions import register_exception_handlers
from .core.logging import configure_logging
from .core.middleware import RequestCounterMiddleware, RequestIdMiddleware
from .db.postgres import close as close_db
from .db.postgres import init_db

settings = get_settings()
configure_logging(settings.log_level)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Postgres equivalent of the old ensure_indexes() call — creates every
    # table/index declared in db/models.py that doesn't already exist yet.
    # Same timing as before: runs once, before the app starts accepting
    # requests.
    await init_db()
    yield
    # Disposes the connection pool on shutdown — same spot the Motor
    # client's close() used to run from.
    await close_db()


def create_app() -> FastAPI:
    app = FastAPI(
        title="MarkdownStack API",
        description="A personal Obsidian-like markdown vault",
        version="1.0.0",
        lifespan=lifespan,
    )

    origins = ["*"]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        # Content-Disposition isn't one of the handful of "simple response
        # headers" CORS exposes to client-side JS by default, so without this
        # the export download's filename (parsed out of that header by the
        # frontend) would silently fall back to a generic name every time.
        expose_headers=["Content-Disposition"],
    )
    # Middleware order here is load-bearing: Starlette applies middleware
    # outside-in in the order add_middleware is called, so CORS (added
    # first) is outermost, RequestIdMiddleware sits inside it, and
    # RequestCounterMiddleware (added last) is innermost.
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(RequestCounterMiddleware)

    register_exception_handlers(app)

    app.include_router(api_router)

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    return app


app = create_app()
