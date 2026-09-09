from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastmcp import FastMCP
from fastmcp.server.dependencies import get_http_headers
from pydantic import Field
from sqlalchemy import func, select, update

from taskrelaymcp.config import Permission, Principal, authenticate
from taskrelaymcp.db import session_scope
from taskrelaymcp.models import Notification, Project, Status, Task
from taskrelaymcp.schemas import TaskCreate, TaskPatch
from taskrelaymcp.services import (
    complete_task as complete,
)
from taskrelaymcp.services import (
    create_task as create,
)
from taskrelaymcp.services import (
    get_task as fetch_task,
)
from taskrelaymcp.services import (
    list_tasks,
    patch_task,
    project_by_key,
    task_dict,
)

TASKRELAY_GUIDE = """# TaskRelay agent guide

TaskRelay is a small shared workspace for work crossing projects, sessions, or agents.

## Identity and lifecycle

- The bearer token grants workspace access; `X-Home-Project` identifies your project.
- Tasks are either `TODO` or immutable `DONE`. Create a new task for follow-up work.
- The server derives an MCP-created task's origin from your Home Project.

## Session workflow

1. Call `get_notifications()` once; it consumes unread completion notifications for your Home Project.
2. Call `get_my_tasks(status="TODO")` and briefly offer relevant work to the user.
3. Do not begin a task without user direction.
4. Use `create_task()` when work should survive the current session.
   Set `target_project` only for cross-project work and include standalone context.
5. Use `update_task()` only while a task is TODO.
6. Use `complete_task(task_id, summary)` only after verification; include concise evidence in the summary.

Use `search_tasks()` before creating likely duplicate work.
Do not use TaskRelay as a chat system, document store, or project-management suite.
"""

mcp = FastMCP(
    "TaskRelay",
    instructions=(
        "TaskRelay coordinates TODO/DONE work using the X-Home-Project identity. "
        "Read the taskrelay://guide resource before first use, then call get_notifications() and get_my_tasks()."
    ),
)


@mcp.resource(
    "taskrelay://guide",
    name="taskrelay-agent-guide",
    title="TaskRelay Agent Guide",
    description="Usage, identity, lifecycle, and session-start guidance for TaskRelay agents.",
    mime_type="text/markdown",
)
def taskrelay_guide() -> str:
    return TASKRELAY_GUIDE


def context(write: bool = False) -> tuple[Principal, str]:
    headers = get_http_headers(include={"authorization", "x-home-project"})
    principal = authenticate(headers.get("authorization"))
    if not principal:
        raise PermissionError("Invalid bearer token")
    if write and principal.permission != Permission.READ_WRITE:
        raise PermissionError("READ_WRITE permission required")
    home = headers.get("x-home-project")
    if not home:
        raise ValueError("X-Home-Project header is required")
    return principal, home


@mcp.tool
def workspace_status() -> dict:
    _, home = context()
    with session_scope() as db:
        project_by_key(db, home)
        list_tasks(db, limit=1)
        counts = dict(db.execute(select(Task.status, func.count()).group_by(Task.status)).all())
        return {"home_project": home, "projects": db.scalar(select(func.count(Project.id))), "tasks_by_status": counts}


@mcp.tool
def get_my_tasks(
    status: Status | None = None,
    tags: list[str] | None = None,
    limit: Annotated[int, Field(ge=1, le=200)] = 100,
) -> list[dict]:
    _, home = context()
    with session_scope() as db:
        tasks = list_tasks(db, project=home, status=status, limit=limit)
        if tags:
            required = set(tags)
            tasks = [task for task in tasks if required.issubset({tag.name for tag in task.tags})]
        return [task_dict(task) for task in tasks]


@mcp.tool
def get_task(task_id: int) -> dict:
    context()
    with session_scope() as db:
        return task_dict(fetch_task(db, task_id))


@mcp.tool
def create_task(
    title: str,
    description: str = "",
    target_project: str | None = None,
    priority: str = "NORMAL",
    tags: list[str] | None = None,
    assigned_agent: str | None = None,
) -> dict:
    _, home = context(write=True)
    with session_scope() as db:
        data = TaskCreate(
            title=title,
            description=description,
            target_project=target_project or home,
            priority=priority,
            tags=tags or [],
            assigned_agent=assigned_agent,
        )
        return task_dict(create(db, data, f"project:{home}", forced_origin=home))


@mcp.tool
def update_task(
    task_id: int,
    title: str | None = None,
    description: str | None = None,
    priority: str | None = None,
    target_project: str | None = None,
    tags: list[str] | None = None,
) -> dict:
    _, home = context(write=True)
    values = {
        key: value for key, value in locals().items() if key not in {"task_id", "home", "_"} and value is not None
    }
    with session_scope() as db:
        return task_dict(patch_task(db, fetch_task(db, task_id), TaskPatch(**values), f"project:{home}"))


@mcp.tool
def complete_task(task_id: int, summary: str) -> dict:
    _, home = context(write=True)
    with session_scope() as db:
        return task_dict(complete(db, fetch_task(db, task_id), f"project:{home}", summary))


@mcp.tool
def get_notifications(unread_only: bool = True, limit: Annotated[int, Field(ge=1, le=200)] = 100) -> list[dict]:
    _, home = context()
    with session_scope() as db:
        project = project_by_key(db, home)
        statement = (
            select(Notification)
            .where(Notification.project_id == project.id)
            .order_by(Notification.created_at.desc())
            .limit(limit)
        )
        if unread_only:
            statement = statement.where(Notification.read_at.is_(None))
        notifications = list(db.scalars(statement))
        if unread_only:
            claimed: list[Notification] = []
            for item in notifications:
                if db.execute(
                    update(Notification)
                    .where(Notification.id == item.id, Notification.read_at.is_(None))
                    .values(read_at=datetime.now(UTC))
                ).rowcount:
                    claimed.append(item)
            notifications = claimed
        result = [
            {
                "id": item.id,
                "task_id": item.task_id,
                "type": item.type,
                "message": item.message,
                "created_at": item.created_at,
            }
            for item in notifications
        ]
        return result


@mcp.tool
def search_tasks(query: str, limit: Annotated[int, Field(ge=1, le=200)] = 50) -> list[dict]:
    context()
    with session_scope() as db:
        return [task_dict(task) for task in list_tasks(db, query=query, limit=limit)]
