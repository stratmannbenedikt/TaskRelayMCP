# TaskRelayMCP

**A small, persistent Todo/Done workspace for humans and MCP agents.** One container serves the React UI, REST API, and MCP endpoint, backed by SQLite.

## Contents

- [TaskRelayMCP](#taskrelaymcp)
  - [Contents](#contents)
  - [Features](#features)
  - [Quick start](#quick-start)
  - [Deploy with GHCR](#deploy-with-ghcr)
  - [OpenCode and authentication](#opencode-and-authentication)
  - [MCP tools](#mcp-tools)
  - [Development and persistence](#development-and-persistence)
    - [Release images](#release-images)
  - [Non-goals](#non-goals)

## Features

- Create, edit, archive, and unarchive focused projects; project keys are immutable.
- Tasks have only `TODO` and immutable `DONE` states. Completing requires a summary; follow-up work is a new task.
- Browser UI refreshes every five seconds while unlocked and on window focus, with browser-local project activity indicators.
- Semantic MCP tools for agent collaboration.
- SQLite persistence in a Docker named volume.

## Quick start

Run the local checks first:

```bash
uv sync --frozen
uv run ruff format --check .
uv run ruff check .
uv run pytest -q
cd frontend && npm ci && npm run build
```

Run the backend locally with [uv](https://docs.astral.sh/uv/):

```bash
export TASKRELAY_DATABASE_URL=sqlite:///./workspace.db
export TASKRELAY_TOKENS='change-me:READ_WRITE,optional-reader:READ'
uv run taskrelaymcp
```

For the React development server:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`, enter the workspace token, then create the first project through `POST /api/projects` or `http://localhost:8080/docs`.

| Surface | Address | Purpose |
| --- | --- | --- |
| UI | `http://localhost:5173` (development) | Project and Todo/Done task view |
| REST API | `/api` | Workspace API |
| OpenAPI | `/docs` | Interactive REST documentation |
| MCP | `/mcp/` | Remote MCP endpoint |

## Deploy with GHCR

`compose.yaml` runs the published production image. Set a real secret outside source control, pull, and start it:

```bash
export TASKRELAY_TOKENS='replace-with-a-long-random-secret:READ_WRITE'
docker compose pull
docker compose up -d
```

The service binds to `127.0.0.1:8080`. Put a TLS-terminating reverse proxy in front of it before remote access; never send bearer tokens over plaintext HTTP.

It defaults to the public `ghcr.io/stratmannbenedikt/taskrelaymcp:latest` image. After publishing the `v0.2.0` tag, pin it with:

```bash
TASKRELAY_IMAGE=ghcr.io/stratmannbenedikt/taskrelaymcp:0.2.0 docker compose up -d
```

For local source builds only, use the unchanged development stack. It has a known loopback-only test token and is not the production Compose file:

```bash
docker compose -f compose.dev.yaml up --build -d
curl -X POST http://localhost:8080/api/projects \
  -H 'Authorization: Bearer taskrelay-local-dev' \
  -H 'Content-Type: application/json' \
  -d '{"key":"taskrelaymcp","name":"TaskRelayMCP"}'
```

Project creation is needed only for a fresh volume; HTTP `409` means it already exists. Stop it with `docker compose -f compose.dev.yaml down`; add `-v` only to delete its test database.

## OpenCode and authentication

`TASKRELAY_TOKENS` is a comma-separated list of `secret:READ` or `secret:READ_WRITE` entries. Authentication is workspace-wide; keep production values in deployment secrets.

Configure the remote MCP client with its token and repository identity:

```json
{
  "mcp": {
    "tasks": {
      "type": "remote",
      "url": "https://tasks.example.com/mcp/",
      "headers": {
        "Authorization": "Bearer {env:TASKS_TOKEN}",
        "X-Home-Project": "project-name"
      }
    }
  }
}
```

Check the remote-MCP environment interpolation syntax for your installed OpenCode version, then restart OpenCode after configuration changes. `X-Home-Project` is configuration, not a credential; task creation derives `origin_project` from it.

For the local Docker test, start a new OpenCode session from this repository after the container is healthy:

```bash
opencode
```

The `taskrelay` MCP tools use `taskrelaymcp` as their Home Project. Tell agents to call `get_notifications()` and `get_my_tasks()` at session start, summarize outstanding work, and ask before beginning.

Tokens grant workspace access (`READ` or `READ_WRITE`), not agent identity. MCP writes are audited as `project:<X-Home-Project>` and derive their origin project from that header; browser/REST writes are audited as `human`. Tasks are only `TODO` or `DONE`; use tags for blocked work. `complete_task(summary)` completes a task permanently and records its summary/activity. Cross-project completion creates the retained `TASK_COMPLETED` notification for the origin project.

## MCP tools

| Tool | Purpose |
| --- | --- |
| `workspace_status` | Summarize the workspace |
| `get_my_tasks` | List Home Project tasks, filterable by `TODO`/`DONE` |
| `get_task` | Read one task |
| `create_task` | Create a task for the Home Project |
| `update_task` | Update a task |
| `complete_task` | Complete a task with a summary |
| `get_notifications` | Consume unread Home Project notifications (or read history with `unread_only=false`) |
| `search_tasks` | Search tasks |

The MCP server also publishes `taskrelay://guide`, a Markdown resource containing identity, lifecycle, and session-start guidance. Server initialization instructions direct clients to it. This is the portable MCP mechanism: Agent Skills remain a client-side convention and are not installed automatically by the server.

## Development and persistence

The single image serves the SPA, REST API, and `/mcp/` on port 8080. The `taskrelay-data` named volume stores `/data/workspace.db`, avoiding host-directory permissions with the non-root container. SQLite uses foreign keys and WAL. Normal application startup is the supported upgrade path: it runs Alembic and safely adopts an unversioned database only when it exactly matches the frozen v0.1 schema signature (tables, columns, constraints, and indexes), then stamps explicit baseline `0001_v01_baseline` before upgrading. Partial or unrelated-table databases are rejected. Use `uv run alembic upgrade head` only for databases already managed by Alembic.

Create a consistent online backup and copy it out:

```bash
docker compose exec taskrelay python -c "import sqlite3; s=sqlite3.connect('/data/workspace.db'); d=sqlite3.connect('/data/workspace.backup.db'); s.backup(d)"
docker cp "$(docker compose ps -q taskrelay):/data/workspace.backup.db" ./workspace.backup.db
```

The UI never reads or consumes agent notifications. Its “New activity” project indicators are stored only in the browser's localStorage: the first visit establishes a baseline, opening a project marks its current activity as seen, and later activity advances show the indicator.

### Release images

GitHub Actions checks Python formatting, linting, tests, and the frontend build on pull requests. After quality passes, it builds the Dockerfile for `linux/amd64`; non-PR runs publish to GHCR with the lowercase repository name. Pushes to `main` publish `main`, a SHA tag, and `latest`; a version tag such as `vX.Y.Z` publishes semantic version tags and a SHA tag. `latest` is published only from the default branch. All workflow actions are pinned to immutable commits.

## Non-goals

Users/teams, per-project ACLs, sprints, milestones, calendars, time tracking, estimates, Git integration, agent orchestration, workflow automation, analytics, and document management. TaskRelay is a persistent coordination scratchpad, not project-management software.
