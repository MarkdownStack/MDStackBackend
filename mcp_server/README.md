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

## Two ways to run this

- **stdio** (default, `MDSTACK_MCP_TRANSPORT` unset): a local subprocess
  Claude Desktop spawns and pipes to directly. This is what "Install /
  test locally" below covers.
- **HTTP** (`MDSTACK_MCP_TRANSPORT=http`): a persistent Streamable HTTP
  service on a port, reachable over the network by multiple clients at
  once instead of spawned fresh per client. This is what "Deploying to
  EC2" below covers — it's the only way to host this somewhere other than
  your own laptop.

## Install / test locally (stdio)

From `backend/`:

```bash
uv sync --extra mcp
```

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

Smoke-test with the MCP Inspector before wiring up any client:

```bash
cd backend
uv run --extra mcp fastmcp dev mcp_server/server.py
```

Run it directly:

```bash
cd backend
uv run --extra mcp python -m mcp_server.server
```

It talks stdio, so running it standalone in a terminal will just look like
it hangs — that's expected. Point an actual MCP client at it instead. (The
`fastmcp` package also ships a `fastmcp run mcp_server/server.py` CLI if you
prefer that over `python -m`; both work identically here.)

### Register with Claude Desktop (local, stdio)

Add to `claude_desktop_config.json` (Settings → Developer → Edit Config,
or `~/Library/Application Support/Claude/claude_desktop_config.json` on
macOS) — as a sibling key of whatever else is already in the file, e.g.
alongside `preferences`, not nested inside it:

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

## Deploying to EC2 (remote, HTTP)

This runs as its own container (`mcp` service in `docker-compose.yml`),
alongside `backend` and `nginx`, on the same `app-network`. Not pulled from
Docker Hub like `backend` — it's built locally on the box, the same way
`nginx` already is (there's no CI job publishing an `mdstack_mcp` image
yet; add one to `.github/workflows/deploy_ec2.yaml`, mirroring
`build-test-push`, if you want that later).

**1. Generate a real bearer token** (this replaces "only my laptop can
spawn this process" — the one thing implicitly protecting stdio mode —
now that it's reachable over the network):

```bash
openssl rand -hex 32
```

**2. Fill in `backend/.env` on the EC2 box** (see `.env.example`):

```bash
MDSTACK_MCP_TOKEN=<the token you just generated>
# Pick ONE way for the tools to act as your vault without an interactive
# auth_login call every session:
MDSTACK_EMAIL=you@example.com
MDSTACK_PASSWORD=your-password
```

**3. Deploy** — same flow the existing CI/CD already uses (`git pull` +
`docker compose up -d --build`), since `mcp`'s `build:` context means the
`--build` flag rebuilds it from whatever's just been pulled, same as
`nginx`. If you're doing it by hand instead:

```bash
cd ~/MDStackBackend   # wherever this repo is cloned on the EC2 box
git pull
docker compose up -d --remove-orphans --pull always --build
```

**4. Verify** — from the EC2 box itself first (bypassing nginx/TLS, to
isolate whether the container itself is healthy):
```bash
docker compose ps mcp          # should show "healthy"
docker compose logs -f mcp     # watch for startup errors
```
Then from anywhere, through nginx:
```bash
curl -i https://api.stalk-my-money.in/mcp
# Expect a 4xx from the MCP protocol layer (this isn't a plain REST GET),
# NOT a connection error / 502 — that's enough to confirm the whole chain
# (DNS → nginx → mcp container) is wired up correctly.
```

**5. Add it as a remote connector.** This is a different config shape than
the local stdio one above — it's a URL + a bearer token, not a spawned
command. In Claude Desktop/Claude.ai: **Settings → Connectors → Add
connector**, enter:
- URL: `https://api.stalk-my-money.in/mcp`
- Auth: Bearer token → the value you generated in step 1

### Security notes

- `MDSTACK_MCP_TOKEN` is the *only* thing standing between the internet and
  write access to your vault once this is live — treat it like any other
  production secret (not committed, rotated if it ever leaks).
- The token check is a single shared static secret (`StaticTokenVerifier`),
  not per-user OAuth — appropriate for "exactly one trusted caller: me",
  not for handing out to other people.
- Everything still rides on the same TLS termination and certs nginx
  already has for the REST API — no new cert/DNS record needed since this
  is exposed as a path (`/mcp`) on the same domain, not a new subdomain.

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
- **Export**: `export_vault` (writes a `.zip` to `MDSTACK_EXPORT_DIR` — in
  http/remote mode, that's on the EC2 box's own disk, not your laptop; see
  the tool's own docstring)

## Not covered

`POST /api/upload` (bulk file/folder import) is deliberately left out — it's
built around a browser's directory-picker semantics (`webkitRelativePath`)
and multipart file uploads, which don't map cleanly onto a tool-call
interface. Use `create_note` repeatedly for a few files, or the web app's
importer for a whole folder tree.

## A note on auth model

Each tool call reuses one in-memory MarkdownStack session (the JWT from
`auth_login`/`MDSTACK_ACCESS_TOKEN`/`MDSTACK_EMAIL`+`MDSTACK_PASSWORD`) for
the life of this server process — in stdio mode that's one process per
Claude Desktop session; in http mode it's one long-running container shared
by every connection, so every caller acts as the same MarkdownStack account
(whichever one `.env` logs in as). There's no per-caller user switching in
http mode — this is built for "one person's vault, hosted remotely," not a
multi-tenant service.
