"""MarkdownStack MCP server.

Exposes the MarkdownStack backend (FastAPI + MongoDB) as MCP tools, so an
MCP client can read and manage a vault the same way the React frontend
does: list/search/create/edit/delete notes and folders, toggle publishing,
and read/vote/comment on published notes across the whole "Explore" feed.

This talks to a *running* backend over HTTP (see client.py) — it does not
open MongoDB itself. Start the FastAPI app first (see backend/README.md),
then point this server at it.

Built on the standalone `fastmcp` package ("FastMCP 2.0" — jlowin/PrefectHQ),
not the official `mcp` SDK's bundled copy. FastMCP 1.0 was folded into that
SDK in 2024 as `mcp.server.fastmcp.FastMCP`, but the SDK's own v2.0 renamed
that class to `MCPServer` and moved the module — so the standalone package
is both the actively-maintained "FastMCP" people mean today and the one that
won't have its import path pulled out from under it by an unrelated SDK
major bump. The decorator API below (`@mcp.tool()`, `mcp.run()`) is the same
either way.

Two ways to run this, both supported (see the try/except import just below):
    - As a package: `python -m mcp_server.server` (cwd=backend/) — what the
      Claude Desktop config in mcp_server/README.md uses, and what the
      Docker image (mcp_server/Dockerfile) runs.
    - As a standalone script: `fastmcp run mcp_server/server.py` / `fastmcp
      dev mcp_server/server.py` / `fastmcp install claude-desktop
      mcp_server/server.py` — the fastmcp CLI always executes the target
      file directly rather than importing it as part of a package, which
      breaks a plain `from .client import ...`.

Transport (env-driven, see MDSTACK_MCP_TRANSPORT below): defaults to stdio
— a local subprocess Claude Desktop spawns and pipes to directly, which is
all a single laptop needs. Set it to "http" to instead run as a persistent
Streamable HTTP service on a port (see mcp_server/README.md's "Deploying to
EC2" section) — that's what turns this into something a *remote* box can
host, reachable over the network by multiple clients instead of spawned
fresh per client. HTTP mode is guarded by a static bearer token
(MDSTACK_MCP_TOKEN) whenever one is set: stdio has no equivalent need for
this (only your own machine can ever spawn that subprocess in the first
place), but a network-reachable HTTP endpoint sitting in front of your vault
absolutely does.

Environment variables:
    MDSTACK_API_BASE_URL   Base URL of the running backend (default: http://localhost:5000)
    MDSTACK_ACCESS_TOKEN   A pre-issued JWT bearer token, if you already have one
    MDSTACK_EMAIL          )  Credentials to auto-login with on first
    MDSTACK_PASSWORD       )  auth-requiring call, if MDSTACK_ACCESS_TOKEN isn't set
    MDSTACK_EXPORT_DIR     Directory export_vault() writes the downloaded .zip
                           into (default: current working directory)
    MDSTACK_MCP_TRANSPORT  "stdio" (default) or "http". Only "http" reads the
                           four vars below.
    MDSTACK_MCP_HOST       Bind address in http mode (default: 0.0.0.0)
    MDSTACK_MCP_PORT       Bind port in http mode (default: 8090)
    MDSTACK_MCP_PATH       URL path the MCP endpoint is served at (default: /mcp)
    MDSTACK_MCP_TOKEN      Shared-secret bearer token required of every caller
                           in http mode. Strongly recommended for anything
                           reachable off localhost — see README. Ignored
                           entirely in stdio mode.

Not covered: /api/upload (bulk file import). That endpoint takes raw
multipart file uploads shaped around a browser's directory picker
(webkitRelativePath) — a poor fit for a tool-call interface. Use
create_note repeatedly for a handful of files, or the web app's importer
for a whole folder tree.
"""
from __future__ import annotations

import os
from typing import Optional

from fastmcp import FastMCP

try:
    from .client import MarkdownStackClient  # package mode: python -m mcp_server.server
except ImportError:
    from client import MarkdownStackClient  # script mode: fastmcp run/dev/install mcp_server/server.py


def _build_auth():
    """Only meaningful for HTTP transport — stdio has no network exposure to
    guard against, so this is skipped entirely there (see run() below).
    A single shared static token is deliberately the whole auth model here:
    this server has exactly one intended caller (whoever you hand the token
    to — your own Claude Desktop/Claude.ai connector), not a multi-tenant
    audience needing real OAuth/user-level scopes."""
    token = os.getenv("MDSTACK_MCP_TOKEN")
    if not token:
        return None
    from fastmcp.server.auth.providers.jwt import StaticTokenVerifier

    return StaticTokenVerifier(tokens={token: {"scopes": ["mcp"]}}, required_scopes=["mcp"])


mcp = FastMCP("markdownstack", auth=_build_auth())
client = MarkdownStackClient()


# ---- Health -----------------------------------------------------------

@mcp.tool()
async def health_check() -> dict:
    """Check that the MarkdownStack backend is reachable at all (no auth needed)."""
    return await client.request_json("GET", "/api/health", auth="none")


# ---- Auth ---------------------------------------------------------------

@mcp.tool()
async def auth_login(email: str, password: str) -> dict:
    """Log in to MarkdownStack with an email + password and cache the JWT for
    the rest of this server's session. Only needed if MDSTACK_ACCESS_TOKEN or
    MDSTACK_EMAIL/MDSTACK_PASSWORD weren't already set in the environment."""
    await client.login(email, password)
    me = await client.request_json("GET", "/api/auth/me")
    return {"status": "logged in", "user": me}


@mcp.tool()
async def auth_register(email: str, password: str) -> dict:
    """Create a new MarkdownStack account. Password must be 8-72 characters.
    Does NOT log in automatically afterwards — call auth_login next."""
    return await client.register(email, password)


@mcp.tool()
async def auth_whoami() -> dict:
    """Return the currently authenticated user's profile (id, email, timestamps)."""
    return await client.request_json("GET", "/api/auth/me")


# ---- Notes (private vault) ----------------------------------------------

@mcp.tool()
async def list_notes(folder_path: Optional[str] = None) -> list:
    """List your notes (title, folder, tags, public status, vote counts —
    not full content). Pass folder_path to filter to one exact folder
    (e.g. "projects/alpha"); omit it to list every note in the vault."""
    params = {}
    if folder_path is not None:
        params["folder_path"] = folder_path
    return await client.request_json("GET", "/api/notes", params=params)


@mcp.tool()
async def get_note(note_id: str) -> dict:
    """Fetch one note's full content, tags, outgoing wikilinks, and the
    other notes in your vault that link back to it (backlinks)."""
    return await client.request_json("GET", f"/api/notes/{note_id}")


@mcp.tool()
async def create_note(title: str, content: str = "", folder_path: str = "") -> dict:
    """Create a new private note. Titles must be unique across your whole
    vault. `content` is markdown — [[wikilinks]] and #tags in it are parsed
    automatically. folder_path="" (default) creates it at the vault root;
    otherwise use a slash-separated path like "projects/alpha" (created
    implicitly if it doesn't exist yet)."""
    payload = {"title": title, "content": content, "folder_path": folder_path}
    return await client.request_json("POST", "/api/notes", json=payload)


@mcp.tool()
async def update_note(
    note_id: str,
    title: Optional[str] = None,
    content: Optional[str] = None,
    folder_path: Optional[str] = None,
    is_public: Optional[bool] = None,
) -> dict:
    """Edit a note. Only fields you pass are changed — omit (leave as None)
    anything you don't want touched. Set is_public=True to publish it to
    the public "Explore" feed and give it a no-login-required URL, or False
    to unpublish it. Renaming to a title you already use elsewhere fails
    (titles are unique per vault)."""
    payload = {}
    if title is not None:
        payload["title"] = title
    if content is not None:
        payload["content"] = content
    if folder_path is not None:
        payload["folder_path"] = folder_path
    if is_public is not None:
        payload["is_public"] = is_public
    return await client.request_json("PUT", f"/api/notes/{note_id}", json=payload)


@mcp.tool()
async def delete_note(note_id: str) -> dict:
    """Permanently delete one note. There's no recycle bin — this can't be undone."""
    await client.request_json("DELETE", f"/api/notes/{note_id}")
    return {"deleted": True, "id": note_id}


@mcp.tool()
async def list_my_published_notes() -> list:
    """List only your own published notes (excerpt, author, upvotes/downvotes,
    comment count) — the same data backing your "My Published Notes" page."""
    return await client.request_json("GET", "/api/notes/published/mine")


# ---- Folders --------------------------------------------------------------

@mcp.tool()
async def list_folders() -> dict:
    """List every folder path in your vault, whether explicitly created or
    only implied by a note living inside it."""
    return await client.request_json("GET", "/api/folders")


@mcp.tool()
async def create_folder(path: str) -> dict:
    """Explicitly create an (empty) folder at the given slash-separated path,
    e.g. "projects/alpha". Fails if a folder already exists at that path."""
    return await client.request_json("POST", "/api/folders", json={"path": path})


@mcp.tool()
async def delete_folder(path: str) -> dict:
    """Delete a folder AND CASCADE: every note directly inside it, every
    subfolder, and every note inside those subfolders too. Irreversible —
    confirm with the user before calling this, same as the web app's own
    confirm dialog. Returns how many notes/folders were removed."""
    return await client.request_json("DELETE", f"/api/folders/{path}")


# ---- Search / tags ----------------------------------------------------

@mcp.tool()
async def search_notes(query: str) -> list:
    """Full-text search your notes' titles + content (MongoDB $text search).
    Returns matches with a short snippet, ranked by relevance."""
    return await client.request_json("GET", "/api/search", params={"q": query})


@mcp.tool()
async def list_tags() -> list:
    """List every #tag used anywhere in your vault, with how many notes use it."""
    return await client.request_json("GET", "/api/tags")


@mcp.tool()
async def notes_with_tag(tag: str) -> list:
    """List every note (in your vault) carrying a given #tag."""
    return await client.request_json("GET", f"/api/tags/{tag}")


# ---- Public / Explore feed (published notes, comments, voting) --------

@mcp.tool()
async def explore_public_notes(limit: int = 100) -> list:
    """Browse published notes across MarkdownStack (the "Explore" feed),
    newest/most-upvoted first, up to `limit` (1-200). If you're logged in
    (auth_login was called, or MDSTACK_ACCESS_TOKEN/EMAIL+PASSWORD were set),
    your own published notes are excluded — this feed is for finding other
    people's notes. Works fully anonymously too."""
    return await client.request_json("GET", "/api/public/notes", params={"limit": limit}, auth="optional")


@mcp.tool()
async def get_public_note(note_id: str) -> dict:
    """Read one published note's full content — no login required. 404s for
    any note that isn't published (or doesn't exist), same response either way."""
    return await client.request_json("GET", f"/api/public/notes/{note_id}", auth="none")


@mcp.tool()
async def vote_public_note(note_id: str, previous: int = 0, next: int = 0) -> dict:
    """Cast (or change) an anonymous up/downvote on a published note. Each of
    `previous`/`next` is -1 (downvote), 0 (no vote), or 1 (upvote) — pass your
    prior vote state as `previous` and the new state as `next` so the server
    applies just the delta (e.g. previous=1, next=-1 flips an upvote straight
    to a downvote in one call). No login required; there's no server-side
    vote-ownership tracking, so this is a soft "temperature", not a
    tamper-proof count."""
    payload = {"previous": previous, "next": next}
    return await client.request_json("POST", f"/api/public/notes/{note_id}/vote", json=payload, auth="none")


@mcp.tool()
async def list_comments(note_id: str) -> list:
    """List the comment thread on a published note, oldest first. No login required."""
    return await client.request_json("GET", f"/api/public/notes/{note_id}/comments", auth="none")


@mcp.tool()
async def create_comment(note_id: str, content: str) -> dict:
    """Post a comment on a published note. Requires being logged in (the
    comment's author is your real account, never a free-typed name)."""
    return await client.request_json(
        "POST", f"/api/public/notes/{note_id}/comments", json={"content": content}
    )


@mcp.tool()
async def upvote_comment(note_id: str, comment_id: str) -> dict:
    """Upvote one comment on a published note. No login required."""
    return await client.request_json(
        "POST", f"/api/public/notes/{note_id}/comments/{comment_id}/upvote", auth="none"
    )


# ---- Export -------------------------------------------------------------

@mcp.tool()
async def export_vault(folder_paths: Optional[list[str]] = None, export_all: bool = False) -> dict:
    """Bundle your vault (or a chosen subset of folders) into a .zip and save
    it to disk, mirroring folder structure exactly so it can be re-imported
    later via the web app's upload feature. Pass export_all=True for the
    whole vault, or folder_paths=["projects/alpha", "journal"] for a subset
    (each entry pulls in that folder, its notes, and everything nested
    under it). Returns the local file path the zip was written to.

    Note: in http/remote mode (see module docstring), "local" means on the
    machine actually running this MCP server (e.g. your EC2 box), not on
    whatever machine the MCP client itself is on — there's no file transfer
    back to the client built into this tool."""
    if not export_all and not folder_paths:
        raise ValueError('Pass export_all=True, or at least one path in folder_paths.')
    payload = {"folder_paths": folder_paths or [], "all": export_all}
    content, filename = await client.request_binary("POST", "/api/export", json=payload)

    export_dir = os.getenv("MDSTACK_EXPORT_DIR") or os.getcwd()
    os.makedirs(export_dir, exist_ok=True)
    out_path = os.path.join(export_dir, filename)
    with open(out_path, "wb") as f:
        f.write(content)

    return {"path": out_path, "filename": filename, "size_bytes": len(content)}


def run() -> None:
    transport = os.getenv("MDSTACK_MCP_TRANSPORT", "stdio")
    if transport == "stdio":
        mcp.run()
        return
    mcp.run(
        transport=transport,  # "http" (Streamable HTTP) or "sse"
        host=os.getenv("MDSTACK_MCP_HOST", "0.0.0.0"),
        port=int(os.getenv("MDSTACK_MCP_PORT", "8090")),
        path=os.getenv("MDSTACK_MCP_PATH", "/mcp"),
    )


if __name__ == "__main__":
    run()
