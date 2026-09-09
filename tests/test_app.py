from __future__ import annotations

import os
from datetime import UTC, datetime

os.environ["TASKRELAY_TOKENS"] = "writer-secret:READ_WRITE,reader-secret:READ"
os.environ["TASKRELAY_DATABASE_URL"] = "sqlite://"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from taskrelaymcp import db
from taskrelaymcp.app import app
from taskrelaymcp.config import Permission
from taskrelaymcp.mcp_server import context, start_task
from taskrelaymcp.models import Base, Comment, Notification, Status, Task, TaskEvent
from taskrelaymcp.schemas import ProjectCreate, TaskCreate, TaskPatch
from taskrelaymcp.services import complete_task, create_project, create_task, list_tasks


@pytest.fixture(autouse=True)
def clean_database():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    db.engine = engine
    db.SessionLocal = sessionmaker(engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    yield
    engine.dispose()


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def headers(token: str = "writer-secret") -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_auth_and_read_only_permissions(client: TestClient) -> None:
    assert client.get("/api/projects").status_code == 401
    response = client.post("/api/projects", headers=headers("reader-secret"), json={"key": "one", "name": "One"})
    assert response.status_code == 403


def test_rest_create_and_filter(client: TestClient) -> None:
    for key in ("origin", "target"):
        assert (
            client.post("/api/projects", headers=headers(), json={"key": key, "name": key.title()}).status_code == 201
        )
    created = client.post(
        "/api/tasks",
        headers=headers(),
        json={
            "title": "Cross-project work",
            "target_project": "target",
            "origin_project": "origin",
            "priority": "HIGH",
            "tags": ["review"],
        },
    )
    assert created.status_code == 201
    tasks = client.get("/api/tasks?project=target&tag=review&priority=HIGH", headers=headers()).json()
    assert [task["title"] for task in tasks] == ["Cross-project work"]


def test_home_origin_and_completion_transaction() -> None:
    with db.session_scope() as session:
        create_project(session, ProjectCreate(key="home", name="Home"))
        create_project(session, ProjectCreate(key="target", name="Target"))
        task = create_task(
            session,
            TaskCreate(title="Ship it", target_project="target", origin_project="target"),
            "agent",
            forced_origin="home",
        )
        task_id = task.id
        assert task.origin_project.key == "home"
        complete_task(session, task, "agent", "Done with evidence")

    with db.session_scope() as session:
        assert session.scalar(select(Comment).where(Comment.task_id == task_id)).body == "Done with evidence"
        assert session.scalar(select(TaskEvent).where(TaskEvent.event_type == "COMPLETED")).task_id == task_id
        notification = session.scalar(select(Notification))
        assert notification.project_id is not None
        assert "Target completed" in notification.message


def test_mcp_mount_requires_auth(client: TestClient) -> None:
    assert client.post("/mcp/", json={}).status_code == 401
    assert client.post("/mcp/", headers=headers(), json={}).status_code != 401


def test_generic_update_cannot_bypass_completion() -> None:
    with pytest.raises(ValueError, match="complete_task"):
        TaskPatch(status="DONE")


def test_current_writes_only_accept_todo_and_done() -> None:
    assert TaskPatch(status="TODO").status == Status.TODO
    with pytest.raises(ValueError):
        TaskPatch(status="IN_PROGRESS")


def test_legacy_statuses_normalize_on_service_access() -> None:
    with db.session_scope() as session:
        project = create_project(session, ProjectCreate(key="home", name="Home"))
        task = Task(
            title="Old task",
            status="BLOCKED",
            target_project=project,
            origin_project=project,
            created_by="agent",
        )
        session.add(task)
        session.flush()
        task_id = task.id
        assert list_tasks(session, project="home")[0].status == Status.TODO
    with db.session_scope() as session:
        assert session.get(Task, task_id).status == Status.TODO


def test_project_summaries_count_and_sort_by_task_activity(client: TestClient) -> None:
    for key in ("alpha", "beta", "empty"):
        response = client.post("/api/projects", headers=headers(), json={"key": key, "name": key.title()})
        assert response.status_code == 201
    alpha = client.post("/api/tasks", headers=headers(), json={"title": "Done", "target_project": "alpha"}).json()
    client.post(f"/api/tasks/{alpha['id']}/complete", headers=headers(), json={"summary": "Finished"})
    beta = client.post("/api/tasks", headers=headers(), json={"title": "Todo", "target_project": "beta"}).json()
    with db.session_scope() as session:
        session.get(Task, alpha["id"]).updated_at = datetime(2030, 1, 1, tzinfo=UTC)
        session.get(Task, beta["id"]).updated_at = datetime(2030, 1, 2, tzinfo=UTC)
    summaries = client.get("/api/projects", headers=headers()).json()
    assert [item["key"] for item in summaries] == ["beta", "alpha", "empty"]
    assert {item["key"]: (item["todo_count"], item["done_count"]) for item in summaries} == {
        "beta": (1, 0),
        "alpha": (0, 1),
        "empty": (0, 0),
    }


def test_mcp_context_separates_home_and_permission(monkeypatch: pytest.MonkeyPatch) -> None:
    def request_headers(**kwargs):
        assert kwargs["include"] == {"authorization", "x-home-project"}
        return {"authorization": "Bearer reader-secret", "x-home-project": "home"}

    monkeypatch.setattr(
        "taskrelaymcp.mcp_server.get_http_headers",
        request_headers,
    )
    principal, home = context()
    assert principal.permission == Permission.READ
    assert home == "home"
    with pytest.raises(PermissionError, match="READ_WRITE"):
        context(write=True)


def test_start_task_keeps_task_todo(monkeypatch: pytest.MonkeyPatch) -> None:
    with db.session_scope() as session:
        project = create_project(session, ProjectCreate(key="home", name="Home"))
        task = Task(
            title="Old", status="IN_PROGRESS", target_project=project, origin_project=project, created_by="agent"
        )
        session.add(task)
        session.flush()
        task_id = task.id
    monkeypatch.setattr(
        "taskrelaymcp.mcp_server.get_http_headers",
        lambda **_: {"authorization": "Bearer writer-secret", "x-home-project": "home"},
    )
    assert start_task(task_id)["status"] == "TODO"
    with db.session_scope() as session:
        assert session.get(Task, task_id).status == Status.TODO


def test_same_project_completion_does_not_notify() -> None:
    with db.session_scope() as session:
        create_project(session, ProjectCreate(key="home", name="Home"))
        task = create_task(session, TaskCreate(title="Local", target_project="home"), "agent", forced_origin="home")
        complete_task(session, task, "agent", "Done")
    with db.session_scope() as session:
        assert session.scalar(select(Notification)) is None
