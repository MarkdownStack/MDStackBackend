# MarkdownStack MCP server

An [MCP](https://modelcontextprotocol.io) server that exposes the MarkdownStack
backend as tools for an MCP client (Claude Desktop, Claude Code, etc.) — list,
search, create, edit, delete, and publish notes; manage folders; and read,
vote on, or comment on anyone's published notes, all through the same REST
API the React frontend uses.

It's a plain HTTP client of a **running backend** (see `client.py`) — it does
not talk to MongoDB directly. Start the FastAPI app first.

## Which "FastMCP"?

This uses the **standalone `fastmcp` package** (`pip install fastmcp` —
originally jlowin's project, now under PrefectHQ; often called "FastMCP
2.0"), not the official low-level `mcp` SDK's bundled copy. Some history,
since it's genuinely confusing:

- FastMCP 1.0 was folded into the official MCP Python SDK in 2024 as
  `mcp.server.fastmcp.FastMCP`.
- jlowin kept developing the standalone project separately as FastMCP 2.0 —
  it's grown well past the bare spec (a client library, auth providers,
  server composition/proxying, OpenAPI-to-MCP generation, testing tools) and
  is the actively-maintained, de facto standard today.
- As of the SDK's own v2.0 (2026), the bundled copy was **renamed** `FastMCP`
  → `MCPServer` and moved modules (`mcp.server.fastmcp` no longer exists in
  `mcp>=2.0`). So pinning to the official SDK's old class name would've been
  one `uv sync` away from an import error the moment that shipped.

Net effect: `pyproject.toml`'s `mcp` extra pins `fastmcp>=2.0,<3` (plus
`httpx`), and `server.py` does `from fastmcp import FastMCP`. The decorator
API (`@mcp.tool()`, `mcp.run()`) is identical either way, so if you ever *do*
want the official SDK's `MCPServer` instead, the tool bodies below barely
change — just the import line and constructor name.

## Install

From `backend/`:

```bash
uv sync --extra mcp
```

This installs `fastmcp` and `httpx` on top of the app's existing locked
dependencies, without touching `app/`'s own dependency set (see the comment
in `pyproject.toml`).

## Configure

Environment variables (all optional except you need *some* way to
authenticate for the write/private tools):

| Variable | Default | Purpose |
|---|---|---|
| `MDSTACK_API_BASE_URL` | `http://localhost:5000` | Base URL of the running backend |
| `MDSTACK_ACCESS_TOKEN` | — | A pre-issued JWT bearer token — skips login entirely |
| `MDSTACK_EMAIL` + `MDSTACK_PASSWORD` | — | Credentials to auto-login with on first auth-requiring call, if no token is set |
| `MDSTACK_EXPORT_DIR` | current directory | Where `export_vault` writes the downloaded `.zip` |

If none of those are set, the server still starts — anonymous tools (reading
published notes, voting, `health_check`, etc.) work immediately, and you can
call the `auth_login` tool at any point during the conversation to unlock the
rest.

## Run it directly (for testing)

```bash
cd backend
uv run --extra mcp python -m mcp_server.server
```

It talks stdio, so running it standalone in a terminal will just look like
it hangs — that's expected. Point an actual MCP client at it instead. (The
`fastmcp` package also ships a `fastmcp run mcp_server/server.py` CLI if you
prefer that over `python -m`; both work identically here.)

## Register with Claude Desktop

Add to `claude_desktop_config.json` (Settings → Developer → Edit Config):

```json
{
  "mcpServers": {
    "markdownstack": {
      "command": "uv",
      "args": [
        "run",
        "--project",
        "/Users/parimal/Projects/obsidian-clone/backend",
        "--extra",
        "mcp",
        "python",
        "-m",
        "mcp_server.server"
      ],
      "env": {
        "MDSTACK_API_BASE_URL": "http://localhost:5000",
        "MDSTACK_EMAIL": "you@example.com",
        "MDSTACK_PASSWORD": "your-password"
      }
    }
  }
}
```

Restart Claude Desktop afterwards. The same `command`/`args`/`env` shape
works for Claude Code's MCP config.

## Tools

- **Health**: `health_check`
- **Auth**: `auth_login`, `auth_register`, `auth_whoami`
- **Notes**: `list_notes`, `get_note`, `create_note`, `update_note`,
  `delete_note`, `list_my_published_notes`
- **Folders**: `list_folders`, `create_folder`, `delete_folder` (cascades —
  irreversible)
- **Search/tags**: `search_notes`, `list_tags`, `notes_with_tag`
- **Public/Explore**: `explore_public_notes`, `get_public_note`,
  `vote_public_note`, `list_comments`, `create_comment`, `upvote_comment`
- **Export**: `export_vault` (writes a `.zip` to `MDSTACK_EXPORT_DIR`)

## Not covered

`POST /api/upload` (bulk file/folder import) is deliberately left out — it's
built around a browser's directory-picker semantics (`webkitRelativePath`)
and multipart file uploads, which don't map cleanly onto a tool-call
interface. Use `create_note` repeatedly for a few files, or the web app's
importer for a whole folder tree.

## A note on auth model

Each tool call reuses one in-memory token for the life of this server
process (it's a single long-running stdio process per MCP client session,
not one process per call) — there's no per-call user switching. If you need
to act as a different account mid-conversation, just call `auth_login` again
with the new credentials.
