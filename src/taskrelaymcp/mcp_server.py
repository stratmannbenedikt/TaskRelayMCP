from __future__ import annotations

from typing import Annotated

from fastmcp import FastMCP
from fastmcp.server.dependencies import get_http_headers
from pydantic import Field
from sqlalchemy import func, select

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

mcp = FastMCP("TaskRelay", instructions="Small shared task workspace. Home project is supplied by X-Home-Project.")


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
    principal, home = context(write=True)
    with session_scope() as db:
        data = TaskCreate(
            title=title,
            description=description,
            target_project=target_project or home,
            priority=priority,
            tags=tags or [],
            assigned_agent=assigned_agent,
        )
        return task_dict(create(db, data, principal.name, forced_origin=home))


@mcp.tool
def update_task(
    task_id: int,
    title: str | None = None,
    description: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    target_project: str | None = None,
    tags: list[str] | None = None,
    assigned_agent: str | None = None,
) -> dict:
    principal, _ = context(write=True)
    values = {
        key: value for key, value in locals().items() if key not in {"task_id", "principal", "_"} and value is not None
    }
    with session_scope() as db:
        return task_dict(patch_task(db, fetch_task(db, task_id), TaskPatch(**values), principal.name))


@mcp.tool
def start_task(task_id: int) -> dict:
    principal, _ = context(write=True)
    with session_scope() as db:
        return task_dict(patch_task(db, fetch_task(db, task_id), TaskPatch(status=Status.TODO), principal.name))


@mcp.tool
def complete_task(task_id: int, summary: str) -> dict:
    principal, _ = context(write=True)
    with session_scope() as db:
        return task_dict(complete(db, fetch_task(db, task_id), principal.name, summary))


@mcp.tool
def get_notifications(unread_only: bool = True) -> list[dict]:
    _, home = context()
    with session_scope() as db:
        project = project_by_key(db, home)
        statement = (
            select(Notification).where(Notification.project_id == project.id).order_by(Notification.created_at.desc())
        )
        if unread_only:
            statement = statement.where(Notification.read_at.is_(None))
        return [
            {
                "id": item.id,
                "task_id": item.task_id,
                "type": item.type,
                "message": item.message,
                "created_at": item.created_at,
            }
            for item in db.scalars(statement)
        ]


@mcp.tool
def search_tasks(query: str, limit: Annotated[int, Field(ge=1, le=200)] = 50) -> list[dict]:
    context()
    with session_scope() as db:
        return [task_dict(task) for task in list_tasks(db, query=query, limit=limit)]
