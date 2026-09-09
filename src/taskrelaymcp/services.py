from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import case, func, or_, select, update
from sqlalchemy.orm import Session, selectinload

from taskrelaymcp.models import Comment, Notification, Project, Status, Tag, Task, TaskEvent
from taskrelaymcp.schemas import ProjectCreate, ProjectPatch, TaskCreate, TaskPatch


class NotFound(ValueError):
    pass


def project_by_key(session: Session, key: str) -> Project:
    project = session.scalar(select(Project).where(Project.key == key))
    if not project:
        raise NotFound(f"Project '{key}' not found")
    return project


def create_project(session: Session, data: ProjectCreate) -> Project:
    project = Project(**data.model_dump())
    session.add(project)
    session.flush()
    return project


def patch_project(session: Session, project: Project, data: ProjectPatch) -> Project:
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(project, key, value)
    session.flush()
    return project


def _tag_objects(session: Session, names: list[str]) -> list[Tag]:
    tags: list[Tag] = []
    for name in sorted({name.strip().lower() for name in names if name.strip()}):
        tag = session.scalar(select(Tag).where(Tag.name == name))
        if not tag:
            tag = Tag(name=name)
            session.add(tag)
        tags.append(tag)
    return tags


def task_query():
    return select(Task).options(
        selectinload(Task.target_project),
        selectinload(Task.origin_project),
        selectinload(Task.tags),
        selectinload(Task.comments),
        selectinload(Task.events),
    )


def normalize_legacy_statuses(session: Session) -> None:
    session.execute(
        update(Task)
        .where(Task.status != Status.DONE)
        .where(Task.status != Status.TODO)
        .values(status=Status.TODO, completed_at=None)
    )


def list_project_summaries(session: Session) -> list[dict]:
    normalize_legacy_statuses(session)
    last_activity = func.coalesce(func.max(Task.updated_at), Project.created_at)
    statement = (
        select(
            Project,
            func.coalesce(func.sum(case((Task.status == Status.TODO, 1), else_=0)), 0).label("todo_count"),
            func.coalesce(func.sum(case((Task.status == Status.DONE, 1), else_=0)), 0).label("done_count"),
            last_activity.label("last_activity_at"),
        )
        .outerjoin(Task, Task.target_project_id == Project.id)
        .group_by(Project.id)
        .order_by(last_activity.desc())
    )
    return [
        {
            "id": project.id,
            "key": project.key,
            "name": project.name,
            "description": project.description,
            "color": project.color,
            "archived": project.archived,
            "created_at": project.created_at,
            "todo_count": todo_count,
            "done_count": done_count,
            "last_activity_at": activity,
        }
        for project, todo_count, done_count, activity in session.execute(statement)
    ]


def get_task(session: Session, task_id: int) -> Task:
    normalize_legacy_statuses(session)
    task = session.scalar(task_query().where(Task.id == task_id))
    if not task:
        raise NotFound(f"Task {task_id} not found")
    return task


def create_task(session: Session, data: TaskCreate, actor: str, forced_origin: str | None = None) -> Task:
    target = project_by_key(session, data.target_project)
    origin = project_by_key(session, forced_origin or data.origin_project or data.target_project)
    task = Task(
        title=data.title,
        description=data.description,
        priority=data.priority,
        target_project=target,
        origin_project=origin,
        created_by=actor,
        assigned_agent=data.assigned_agent,
        tags=_tag_objects(session, data.tags),
    )
    session.add(task)
    session.flush()
    session.add(TaskEvent(task_id=task.id, actor=actor, event_type="CREATED"))
    session.flush()
    return get_task(session, task.id)


def patch_task(session: Session, task: Task, data: TaskPatch, actor: str) -> Task:
    changes = data.model_dump(exclude_unset=True)
    if "target_project" in changes:
        task.target_project = project_by_key(session, changes.pop("target_project"))
    if "tags" in changes:
        task.tags = _tag_objects(session, changes.pop("tags") or [])
    previous_status = task.status
    for key, value in changes.items():
        setattr(task, key, value)
    if task.status == Status.DONE and previous_status != Status.DONE:
        task.completed_at = datetime.now(UTC)
    elif task.status != Status.DONE:
        task.completed_at = None
    session.flush()
    session.add(
        TaskEvent(
            task_id=task.id,
            actor=actor,
            event_type="UPDATED",
            payload_json=json.dumps(data.model_dump(exclude_unset=True), default=str),
        )
    )
    session.flush()
    return get_task(session, task.id)


def add_comment(session: Session, task: Task, actor: str, body: str) -> Task:
    session.add(Comment(task_id=task.id, author=actor, body=body))
    session.add(TaskEvent(task_id=task.id, actor=actor, event_type="COMMENTED"))
    session.flush()
    return get_task(session, task.id)


def complete_task(session: Session, task: Task, actor: str, summary: str) -> Task:
    task.status = Status.DONE
    task.completed_at = datetime.now(UTC)
    session.add(Comment(task_id=task.id, author=actor, body=summary))
    session.add(
        TaskEvent(task_id=task.id, actor=actor, event_type="COMPLETED", payload_json=json.dumps({"summary": summary}))
    )
    if task.origin_project_id != task.target_project_id:
        session.add(
            Notification(
                project_id=task.origin_project_id,
                task_id=task.id,
                type="TASK_COMPLETED",
                message=f"{task.target_project.name} completed #{task.id}: {task.title}",
            )
        )
    session.flush()
    return get_task(session, task.id)


def list_tasks(
    session: Session,
    *,
    project: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    tag: str | None = None,
    query: str | None = None,
    limit: int = 100,
) -> list[Task]:
    normalize_legacy_statuses(session)
    statement = task_query().order_by(Task.updated_at.desc()).limit(min(limit, 200))
    if project:
        statement = statement.join(Task.target_project).where(Project.key == project)
    if status:
        statement = statement.where(Task.status == status)
    if priority:
        statement = statement.where(Task.priority == priority)
    if tag:
        statement = statement.join(Task.tags).where(Tag.name == tag)
    if query:
        pattern = f"%{query}%"
        statement = statement.where(or_(Task.title.ilike(pattern), Task.description.ilike(pattern)))
    return list(session.scalars(statement).unique())


def task_dict(task: Task) -> dict:
    return {
        "id": task.id,
        "title": task.title,
        "description": task.description,
        "status": task.status,
        "priority": task.priority,
        "target_project": task.target_project.key,
        "origin_project": task.origin_project.key,
        "created_by": task.created_by,
        "assigned_agent": task.assigned_agent,
        "tags": [tag.name for tag in task.tags],
        "comments": [
            {"id": item.id, "author": item.author, "body": item.body, "created_at": item.created_at}
            for item in task.comments
        ],
        "events": [
            {
                "id": item.id,
                "actor": item.actor,
                "type": item.event_type,
                "payload": json.loads(item.payload_json),
                "created_at": item.created_at,
            }
            for item in task.events
        ],
        "created_at": task.created_at,
        "updated_at": task.updated_at,
        "completed_at": task.completed_at,
    }
