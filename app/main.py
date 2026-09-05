import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from .database import ensure_indexes
from .routers import auth, notes, folders, search, tags, upload, public, export

load_dotenv()

app = FastAPI(title="MarkdownStack API", description="A personal Obsidian-like markdown vault", version="1.0.0")

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

app.include_router(auth.router)
app.include_router(notes.router)
app.include_router(folders.router)
app.include_router(search.router)
app.include_router(tags.router)
app.include_router(upload.router)
app.include_router(public.router)
app.include_router(export.router)


@app.on_event("startup")
async def on_startup():
    await ensure_indexes()


@app.get("/api/health")
async def health():
    return {"status": "ok"}
