# TaskRelayMCP

A small private-team Todo/Done workspace for humans and MCP agents. One container serves the Angular client-side UI, REST API, and MCP endpoint, backed by SQLite.

## Features

- Local username/password accounts administered by a bootstrap administrator.
- Private projects with exactly one owner and optional members.
- Named, revocable, user-owned MCP keys.
- Membership-filtered REST and MCP reads, search, counts, tags, assignments, and notifications.
- Explicit, audited, read-only administrator inspection mode.
- Tasks have only `TODO` and immutable `DONE` states.
- Project Notes support nested folders, safe Markdown preview, same-project wiki links, backlinks, and revision restore; MCP exposes explicit note and folder operations.
- Home (`/home`), global Tasks (`/tasks`), and global Notes (`/notes`) separate workspace navigation from project editing routes; `/projects` redirects to Home for compatibility.

## Run locally

```bash
export TASKRELAY_DATABASE_URL=sqlite:///./workspace.db
export TASKRELAY_ADMIN_USERNAME=admin
export TASKRELAY_ADMIN_PASSWORD='replace-with-a-long-secret'
export TASKRELAY_ADMIN_DISPLAY_NAME='Administrator'
export TASKRELAY_SECURE_COOKIES=false  # local HTTP only
export TASKRELAY_PUBLIC_ORIGIN=http://localhost:8080
uv run taskrelaymcp
```

Open `http://localhost:8080`. Production deployments must retain the default secure-cookie setting and terminate TLS in front of the service.

For frontend development:

```bash
cd frontend
npm ci
npm run dev
```

The checked-in development Compose stack uses loopback-only ports and known local credentials (`admin` / `taskrelay-local-password`); never use it in production.

## Browser E2E checks

Install Chromium once, then run the browser suite from `frontend/`:

```bash
npm run e2e:install
npm run e2e
```

`e2e` builds the Angular client and starts a fresh FastAPI server on `127.0.0.1:18080` with a temporary `/tmp/taskrelay-playwright.db`, loopback-only insecure cookies, and an E2E bootstrap administrator. It covers project capabilities, owner settings, and responsive global navigation. It removes that database after the run and never reuses an existing server.

## Production Compose

```bash
export TASKRELAY_ADMIN_USERNAME=admin
export TASKRELAY_ADMIN_PASSWORD='replace-with-a-long-random-secret'
export TASKRELAY_PUBLIC_ORIGIN=https://tasks.example.com
docker compose pull
docker compose up -d
```

Pin release `v0.5.0` with:

```bash
TASKRELAY_IMAGE=ghcr.io/stratmannbenedikt/taskrelaymcp:0.5.0 docker compose up -d
```

The service binds to `127.0.0.1:8080`. Use a TLS-terminating reverse proxy and set `TASKRELAY_PUBLIC_ORIGIN` to its public origin (for example, `https://tasks.example.com`). `TASKRELAY_SECURE_COOKIES` defaults to `true`; disabling it is only for loopback HTTP development.

## MCP authentication

Create a named key under **Account → MCP keys**. Its secret is shown once and stored only as a SHA-256 hash. Configure that key and a Home Project of which its user is a member:

```json
{
  "mcp": {
    "tasks": {
      "type": "remote",
      "url": "https://tasks.example.com/mcp/",
      "headers": {
        "Authorization": "Bearer {env:TASKRELAY_MCP_KEY}",
        "X-Home-Project": "project-name"
      }
    }
  }
}
```

Available tools include task, note, an
 folder read/write/move/archive operations. MCP writes record the owning user, channel, and key name. Notification consumption is per user; browser reads never consume MCP notifications.

## Tags

Tags are colored, project-scoped definitions. Project members manage them from **Manage tags** on a project's Tasks page: create a lowercase slug with a color and description, edit color/description, and (owners) rename or archive. REST lists `TagOut` objects at `GET /api/tags` and
`GET /api/projects/{key}/tags`; browser task create/patch uses `tag_ids: [int]`. Archived tags remain
on historical tasks but cannot be assigned. MCP agents list active definitions with `list_project_tags()`
and may assign existing names; `create_project_tag()` requires elicited confirmation and otherwise returns
`{"status":"ELICITATION_UNSUPPORTED","fallback_tool":"propose_project_tag"}`. Proposals are approved or
rejected only through the browser API.

## Upgrade to v0.4

Pre-0.4 development databases and volumes must be reset once before starting v0.4; they are not compatible with the new baseline. The project-tag baseline is also pre-deployment: reset disposable development data rather than applying it to an existing volume. Back up any data you need first, remove the old development volume or database, then start normally. Alembic initializes the baseline and applies future schema upgrades.

## Development checks

```bash
uv sync --frozen
uv run ruff format --check .
uv run ruff check .
npm --prefix frontend ci
npm --prefix frontend run build
npm --prefix frontend test -- --watch=false
uv run pytest -q
```

## Persistence and backup

The production named volume stores `/data/workspace.db`. SQLite foreign keys and WAL are enabled.

```bash
docker compose exec taskrelay python -c "import sqlite3; s=sqlite3.connect('/data/workspace.db'); d=sqlite3.connect('/data/workspace.backup.db'); s.backup(d)"
docker cp "$(docker compose ps -q taskrelay):/data/workspace.backup.db" ./workspace.backup.db
```

## Non-goals

Organizations, public registration, email, invitations, viewer roles, multiple assignees, granular task ACLs, time tracking, OAuth, external identity providers, billing, Kubernetes, and workflow expansion.
