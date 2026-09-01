import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from .database import ensure_indexes
from .routers import auth, notes, folders, search, graph, tags

load_dotenv()

app = FastAPI(title="Vault API", description="A personal Obsidian-like markdown vault", version="1.0.0")

origins = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(notes.router)
app.include_router(folders.router)
app.include_router(search.router)
app.include_router(graph.router)
app.include_router(tags.router)


@app.on_event("startup")
async def on_startup():
    await ensure_indexes()


@app.get("/api/health")
async def health():
    return {"status": "ok"}
