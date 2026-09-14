from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .core.config import get_settings
from .core.exceptions import register_exception_handlers
from .core.logging import configure_logging
from .core.middleware import RequestCounterMiddleware, RequestIdMiddleware
from .db.indexes import ensure_indexes
from .db.mongo import close as close_mongo
from .routers import admin, auth, export, folders, notes, public, search, tags, upload

settings = get_settings()
configure_logging(settings.log_level)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Replaces the deprecated @app.on_event("startup") — same single call,
    # same timing (before the app starts accepting requests).
    await ensure_indexes()
    yield
    # New: today's Motor client is never closed at all. Closing it on
    # shutdown doesn't change anything a caller can observe.
    await close_mongo()


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
    # RequestCounterMiddleware (added last) is innermost — preserving the
    # original "counter runs after CORS" property from app/main.py.
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(RequestCounterMiddleware)

    register_exception_handlers(app)

    app.include_router(auth.router)
    app.include_router(notes.router)
    app.include_router(folders.router)
    app.include_router(search.router)
    app.include_router(tags.router)
    app.include_router(upload.router)
    app.include_router(public.router)
    app.include_router(export.router)
    app.include_router(admin.router)

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    return app


app = create_app()
