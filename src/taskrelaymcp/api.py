from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from taskrelaymcp.auth import CurrentPrincipal, Writer
from taskrelaymcp.db import session_scope
from taskrelaymcp.models import Project, Status, Tag
from taskrelaymcp.schemas import (
    CompleteTask,
    ProjectCreate,
    ProjectOut,
    ProjectPatch,
    ProjectSummaryOut,
    TaskCreate,
    TaskOut,
    TaskPatch,
)
from taskrelaymcp.services import (
    Conflict,
    NotFound,
    complete_task,
    create_project,
    create_task,
    get_task,
    list_project_summaries,
    list_tasks,
    patch_project,
    patch_task,
    project_by_key,
    task_dict,
)
from taskrelaymcp.services import (
    delete_task as remove_task,
)

router = APIRouter(prefix="/api", tags=["api"])


def db_session():
    with session_scope() as session:
        yield session


DB = Annotated[Session, Depends(db_session)]


def missing(exc: NotFound) -> HTTPException:
    return HTTPException(404, str(exc))


@router.get("/projects", response_model=list[ProjectSummaryOut])
def projects(_: CurrentPrincipal, db: DB, include_archived: bool = False) -> list[dict]:
    return list_project_summaries(db, include_archived)


@router.post("/projects", response_model=ProjectOut, status_code=201)
def add_project(data: ProjectCreate, principal: Writer, db: DB) -> Project:
    try:
        return create_project(db, data)
    except IntegrityError as exc:
        raise HTTPException(409, "Project key already exists") from exc


@router.patch("/projects/{key}", response_model=ProjectOut)
def update_project(key: str, data: ProjectPatch, _: Writer, db: DB) -> Project:
    try:
        return patch_project(db, project_by_key(db, key), data)
    except NotFound as exc:
        raise missing(exc) from exc


@router.get("/tasks", response_model=list[TaskOut])
def tasks(
    _: CurrentPrincipal,
    db: DB,
    project: str | None = None,
    status: Status | None = None,
    priority: str | None = None,
    tag: str | None = None,
    q: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[dict]:
    return [
        task_dict(task)
        for task in list_tasks(db, project=project, status=status, priority=priority, tag=tag, query=q, limit=limit)
    ]


@router.post("/tasks", response_model=TaskOut, status_code=201)
def add_task(data: TaskCreate, _: Writer, db: DB) -> dict:
    try:
        return task_dict(create_task(db, data, "human"))
    except NotFound as exc:
        raise missing(exc) from exc


@router.get("/tasks/{task_id}", response_model=TaskOut)
def task(task_id: int, _: CurrentPrincipal, db: DB) -> dict:
    try:
        return task_dict(get_task(db, task_id))
    except NotFound as exc:
        raise missing(exc) from exc


@router.patch("/tasks/{task_id}", response_model=TaskOut)
def update_task(task_id: int, data: TaskPatch, _: Writer, db: DB) -> dict:
    try:
        return task_dict(patch_task(db, get_task(db, task_id), data, "human"))
    except NotFound as exc:
        raise missing(exc) from exc
    except Conflict as exc:
        raise HTTPException(409, str(exc)) from exc


@router.delete("/tasks/{task_id}", status_code=204)
def delete_task(task_id: int, _: Writer, db: DB) -> Response:
    try:
        remove_task(db, get_task(db, task_id))
    except NotFound as exc:
        raise missing(exc) from exc
    except Conflict as exc:
        raise HTTPException(409, str(exc)) from exc
    return Response(status_code=204)


@router.post("/tasks/{task_id}/complete", response_model=TaskOut)
def finish(task_id: int, data: CompleteTask, _: Writer, db: DB) -> dict:
    try:
        return task_dict(complete_task(db, get_task(db, task_id), "human", data.summary))
    except NotFound as exc:
        raise missing(exc) from exc
    except Conflict as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/tags", response_model=list[str])
def tags(_: CurrentPrincipal, db: DB) -> list[str]:
    return list(db.scalars(select(Tag.name).order_by(Tag.name)))
