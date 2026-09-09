# 0001 — Keep TaskRelay a small coordination service

## Decision

- One workspace per deployment, with workspace-wide READ or READ_WRITE bearer tokens.
- The independent `X-Home-Project` MCP header identifies an agent's repository context.
- MCP task origins are server-derived from Home Project; targets may be cross-project.
- Tasks have only `TODO` and `DONE` workflow states; blocking remains descriptive metadata such as a tag.
- REST and semantic MCP tools share one service layer and SQLite database.
- One image serves the built React SPA, REST API, and MCP endpoint.
- V1 initializes an empty schema directly. Introduce Alembic before changing a deployed schema.

## Non-goals

No users/teams, per-project ACLs, sprints, milestones, estimates, Git integration, orchestration, workflow engine, analytics platform, or document management.
