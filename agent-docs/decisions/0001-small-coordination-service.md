# 0001 — Keep TaskRelay a small coordination service

## Decision

- One workspace per deployment, with workspace-wide READ or READ_WRITE bearer tokens.
- The independent `X-Home-Project` MCP header identifies an agent's repository context.
- MCP activity is attributed to `project:<home-key>`; tokens identify workspace access, not agents.
- MCP task origins are server-derived from Home Project; targets may be cross-project.
- Tasks have only `TODO` and `DONE` workflow states; blocking remains descriptive metadata such as a tag.
- `DONE` tasks are immutable; follow-up work is represented by a new task rather than reopening.
- Agent notifications are consumed through MCP; browser project-change indicators remain local to that browser.
- REST and semantic MCP tools share one service layer and SQLite database.
- One image serves the built React SPA, REST API, and MCP endpoint.
- Alembic owns schema initialization and upgrades; unversioned v0.1 databases are adopted only after exact frozen-schema validation.

## Non-goals

No users/teams, per-project ACLs, sprints, milestones, estimates, Git integration, orchestration, workflow engine, analytics platform, or document management.
