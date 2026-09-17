from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastmcp import Context, FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_http_headers
from pydantic import Field
from sqlalchemy import func, or_, select
from sqlalchemy.dialects.sqlite import insert

from taskrelaymcp.auth import authenticate_mcp
from taskrelaymcp.config import Principal
from taskrelaymcp.db import session_scope
from taskrelaymcp.models import Notification, NotificationRead, Project, ProjectMembership, Status, Tag, Task
from taskrelaymcp.schemas import (
    NoteCreate,
    NoteFolderCreate,
    NoteFolderPatch,
    NotePatch,
    TagCreate,
    TaskCreate,
    TaskPatch,
)
from taskrelaymcp.services import (
    NotFound,
    _folder,
    _note,
    create_tag,
    create_tag_proposal,
    folder_dict,
    list_tasks,
    membership,
    note_dict,
    patch_note,
    patch_note_folder,
    patch_task,
    project_by_key,
    proposal_dict,
    tag_dict,
    task_dict,
)
from taskrelaymcp.services import complete_task as complete
from taskrelaymcp.services import (
    create_note as create_note_record,
)
from taskrelaymcp.services import (
    create_note_folder as create_note_folder_record,
)
from taskrelaymcp.services import create_task as create
from taskrelaymcp.services import (
    get_tag_proposal as fetch_tag_proposal,
)
from taskrelaymcp.services import get_task as fetch_task
from taskrelaymcp.services import (
    list_note_folders as list_note_folder_records,
)
from taskrelaymcp.services import (
    list_notes as list_note_records,
)

TASKRELAY_GUIDE = """# TaskRelay agent guide

TaskRelay is a private team workspace for work crossing projects, sessions, or agents.

- Your named bearer key acts as its owning user; `X-Home-Project` must be one of that user's projects.
- Tasks are either `TODO` or immutable `DONE`. Create a new task for follow-up work.
- Call `get_notifications()` and `get_my_tasks()` at session start.
- Cross-project creation and movement require membership in both projects.
- Use `complete_task(task_id, summary)` only after verification.
- Call `list_project_tags()` before assigning tags. Task tags must already be active in the target project.
- Use `create_project_tag()` only when the user can confirm it. If elicitation is unsupported, call
  `propose_project_tag()`; never propose automatically after a decline or cancellation.
"""

mcp = FastMCP(
    "TaskRelay",
    instructions="Read taskrelay://guide before first use, then call get_notifications() and get_my_tasks().",
)


@mcp.resource(
    "taskrelay://guide",
    name="taskrelay-agent-guide",
    title="TaskRelay Agent Guide",
    description="Authentication, project access, lifecycle, and session-start guidance.",
    mime_type="text/markdown",
)
def taskrelay_guide() -> str:
    return TASKRELAY_GUIDE


def context() -> tuple[Principal, str]:
    headers = get_http_headers(include={"authorization", "x-home-project"})
    with session_scope() as db:
        principal = authenticate_mcp(db, headers.get("authorization"))
        if not principal:
            raise PermissionError("Invalid or revoked MCP key")
        home = headers.get("x-home-project")
        if not home:
            raise ValueError("X-Home-Project header is required")
        try:
            project = project_by_key(db, home)
        except NotFound as exc:
            raise PermissionError("Home project not found") from exc
        if not membership(db, project.id, principal.user_id):
            raise PermissionError("Home project not found")
        return principal, home


@mcp.tool
def workspace_status() -> dict:
    principal, home = context()
    with session_scope() as db:
        project_ids = select(ProjectMembership.project_id).where(ProjectMembership.user_id == principal.user_id)
        accessible = or_(Task.target_project_id.in_(project_ids), Task.origin_project_id.in_(project_ids))
        counts = dict(db.execute(select(Task.status, func.count()).where(accessible).group_by(Task.status)).all())
        return {
            "home_project": home,
            "projects": db.scalar(select(func.count(Project.id)).where(Project.id.in_(project_ids))),
            "tasks_by_status": counts,
        }


@mcp.tool
def get_my_tasks(
    status: Status | None = None,
    tags: list[str] | None = None,
    limit: Annotated[int, Field(ge=1, le=200)] = 100,
) -> list[dict]:
    principal, home = context()
    with session_scope() as db:
        tasks = list_tasks(db, principal, project=home, status=status, limit=limit)
        if tags:
            required = set(tags)
            tasks = [task for task in tasks if required.issubset({tag.name for tag in task.tags})]
        return [task_dict(task) for task in tasks]


@mcp.tool
def get_task(task_id: int) -> dict:
    principal, _ = context()
    with session_scope() as db:
        return task_dict(fetch_task(db, task_id, principal))


@mcp.tool
def create_task(
    title: str,
    description: str = "",
    target_project: str | None = None,
    priority: str = "NORMAL",
    tags: list[str] | None = None,
    assigned_user: str | None = None,
) -> dict:
    principal, home = context()
    with session_scope() as db:
        target = target_project or home
        data = TaskCreate(
            title=title,
            description=description,
            target_project=target,
            priority=priority,
            tag_ids=_tag_ids(db, target, tags or [], principal),
            assigned_user=assigned_user,
        )
        return task_dict(create(db, data, principal, forced_origin=home))


@mcp.tool
def update_task(
    task_id: int,
    title: str | None = None,
    description: str | None = None,
    priority: str | None = None,
    target_project: str | None = None,
    tags: list[str] | None = None,
    assigned_user: str | None = None,
) -> dict:
    principal, _ = context()
    values = {
        key: value for key, value in locals().items() if key not in {"task_id", "principal", "_"} and value is not None
    }
    with session_scope() as db:
        task = fetch_task(db, task_id, principal)
        if "tags" in values:
            target = values.get("target_project", task.target_project.key)
            values["tag_ids"] = _tag_ids(db, target, values.pop("tags"), principal)
        return task_dict(patch_task(db, task, TaskPatch(**values), principal))


def _tag_ids(db, project_key: str, names: list[str], principal: Principal) -> list[int]:
    normalized = [name.strip().lower() for name in names if name.strip()]
    try:
        project = project_by_key(db, project_key, principal)
    except NotFound as exc:
        raise ValueError("Target project not found") from exc
    tags = list(
        db.scalars(select(Tag).where(Tag.project_id == project.id, Tag.name.in_(normalized), Tag.archived_at.is_(None)))
    )
    found = {tag.name for tag in tags}
    unknown = sorted(set(normalized) - found)
    if unknown:
        raise ValueError(
            f"Unknown or archived tags: {', '.join(unknown)}. Use list_project_tags(), "
            "create_project_tag(), then propose_project_tag() only if elicitation is unsupported."
        )
    return [tag.id for tag in tags]


@mcp.tool
def list_project_tags(include_archived: bool = False) -> list[dict]:
    principal, home = context()
    with session_scope() as db:
        project = project_by_key(db, home, principal)
        tags = select(Tag).where(Tag.project_id == project.id).order_by(Tag.name)
        if not include_archived:
            tags = tags.where(Tag.archived_at.is_(None))
        return [tag_dict(db, tag) for tag in db.scalars(tags)]


def _elicitation_unsupported(exc: ToolError) -> bool:
    message = str(exc).lower()
    return "elicit" in message and ("support" in message or "modern" in message or "back-channel" in message)


@mcp.tool
async def create_project_tag(name: str, color: str, ctx: Context, description: str = "") -> dict:
    """Request user confirmation before creating a home-project tag."""
    tag_data = TagCreate(name=name, color=color, description=description)
    try:
        result = await ctx.elicit(
            f"Create tag '{tag_data.name}' ({tag_data.color}) in the home project?",
            response_type=bool,
            response_title="Create project tag",
        )
    except ToolError as exc:
        if _elicitation_unsupported(exc):
            return {"status": "ELICITATION_UNSUPPORTED", "fallback_tool": "propose_project_tag"}
        raise
    if result.action == "decline":
        return {"status": "DECLINED"}
    if result.action == "cancel":
        return {"status": "CANCELLED"}
    if not result.data:
        return {"status": "DECLINED"}
    principal, home = context()
    with session_scope() as db:
        tag = create_tag(db, project_by_key(db, home, principal), **tag_data.model_dump(), principal=principal)
        return {"status": "CREATED", "tag": tag_dict(db, tag)}


@mcp.tool
def propose_project_tag(
    name: str, color: str, description: str = "", apply_to_task_ids: list[int] | None = None
) -> dict:
    principal, home = context()
    tag_data = TagCreate(name=name, color=color, description=description)
    with session_scope() as db:
        proposal = create_tag_proposal(
            db,
            project_by_key(db, home, principal),
            **tag_data.model_dump(),
            task_ids=apply_to_task_ids or [],
            principal=principal,
        )
        return proposal_dict(proposal)


@mcp.tool
def get_tag_proposal(proposal_id: int) -> dict:
    principal, _ = context()
    with session_scope() as db:
        return proposal_dict(fetch_tag_proposal(db, proposal_id, principal))


@mcp.tool
def complete_task(task_id: int, summary: str) -> dict:
    principal, _ = context()
    with session_scope() as db:
        return task_dict(complete(db, fetch_task(db, task_id, principal), principal, summary))


@mcp.tool
def get_notifications(unread_only: bool = True, limit: Annotated[int, Field(ge=1, le=200)] = 100) -> list[dict]:
    principal, home = context()
    with session_scope() as db:
        project = project_by_key(db, home, principal)
        read = select(NotificationRead.notification_id).where(NotificationRead.user_id == principal.user_id)
        statement = (
            select(Notification)
            .where(Notification.project_id == project.id)
            .order_by(Notification.created_at.desc())
            .limit(limit)
        )
        if unread_only:
            statement = statement.where(Notification.id.not_in(read))
        notifications = list(db.scalars(statement))
        if unread_only and notifications:
            now = datetime.now(UTC)
            claimed_ids = set(
                db.scalars(
                    insert(NotificationRead)
                    .values(
                        [
                            {"notification_id": item.id, "user_id": principal.user_id, "read_at": now}
                            for item in notifications
                        ]
                    )
                    .on_conflict_do_nothing(index_elements=["notification_id", "user_id"])
                    .returning(NotificationRead.notification_id)
                )
            )
            notifications = [item for item in notifications if item.id in claimed_ids]
        return [
            {
                "id": item.id,
                "task_id": item.task_id,
                "type": item.type,
                "message": item.message,
                "created_at": item.created_at,
            }
            for item in notifications
        ]


@mcp.tool
def search_tasks(query: str, limit: Annotated[int, Field(ge=1, le=200)] = 50) -> list[dict]:
    principal, _ = context()
    with session_scope() as db:
        return [task_dict(task) for task in list_tasks(db, principal, query=query, limit=limit)]


def _home_project(db, principal: Principal, home: str) -> Project:
    project = project_by_key(db, home, principal)
    if not project.notes_enabled:
        raise ValueError("Notes are disabled for the home project")
    return project


def _home_note(db, principal: Principal, home: str, note_id: int):
    note = _note(db, note_id, principal)
    if note.project.key != home:
        raise ValueError("Note not found")
    return note


@mcp.tool
def list_note_folders() -> list[dict]:
    principal, home = context()
    with session_scope() as db:
        project = _home_project(db, principal, home)
        return [folder_dict(folder) for folder in list_note_folder_records(db, project, principal)]


@mcp.tool
def list_notes(query: str | None = None, limit: Annotated[int, Field(ge=1, le=200)] = 100) -> list[dict]:
    principal, home = context()
    with session_scope() as db:
        project = _home_project(db, principal, home)
        return [note_dict(note) for note in list_note_records(db, project, principal, query, limit=limit)]


@mcp.tool
def get_note(note_id: int) -> dict:
    principal, home = context()
    with session_scope() as db:
        _home_project(db, principal, home)
        return note_dict(_home_note(db, principal, home, note_id), db)


@mcp.tool
def search_notes(query: str, limit: Annotated[int, Field(ge=1, le=200)] = 50) -> list[dict]:
    return list_notes(query, limit)


@mcp.tool
def create_note(title: str, markdown: str, folder_id: int | None = None) -> dict:
    principal, home = context()
    with session_scope() as db:
        project = _home_project(db, principal, home)
        return note_dict(
            create_note_record(db, project, NoteCreate(title=title, markdown=markdown, folder_id=folder_id), principal),
            db,
        )


@mcp.tool
def update_note(
    note_id: int,
    expected_version: int,
    title: str | None = None,
    markdown: str | None = None,
    folder_id: int | None = None,
) -> dict:
    principal, home = context()
    values: dict[str, object] = {"expected_version": expected_version}
    if title is not None:
        values["title"] = title
    if markdown is not None:
        values["markdown"] = markdown
    if folder_id is not None:
        values["folder_id"] = folder_id
    with session_scope() as db:
        _home_project(db, principal, home)
        return note_dict(patch_note(db, _home_note(db, principal, home, note_id), NotePatch(**values), principal), db)


@mcp.tool
def move_note(note_id: int, folder_id: int | None, expected_version: int) -> dict:
    principal, home = context()
    with session_scope() as db:
        _home_project(db, principal, home)
        data = NotePatch(folder_id=folder_id, expected_version=expected_version)
        return note_dict(patch_note(db, _home_note(db, principal, home, note_id), data, principal), db)


@mcp.tool
def create_note_folder(name: str, parent_id: int | None = None) -> dict:
    principal, home = context()
    with session_scope() as db:
        project = _home_project(db, principal, home)
        return folder_dict(
            create_note_folder_record(db, project, NoteFolderCreate(name=name, parent_id=parent_id), principal)
        )


@mcp.tool
def move_note_folder(folder_id: int, parent_id: int | None = None) -> dict:
    principal, home = context()
    with session_scope() as db:
        _home_project(db, principal, home)
        folder = _folder(db, folder_id, principal)
        if folder.project.key != home:
            raise ValueError("Folder not found")
        return folder_dict(patch_note_folder(db, folder, NoteFolderPatch(parent_id=parent_id), principal))


@mcp.tool
def archive_note(note_id: int, expected_version: int, archived: bool = True) -> dict:
    principal, home = context()
    with session_scope() as db:
        _home_project(db, principal, home)
        return note_dict(
            patch_note(
                db,
                _home_note(db, principal, home, note_id),
                NotePatch(archived=archived, expected_version=expected_version),
                principal,
            ),
            db,
        )
