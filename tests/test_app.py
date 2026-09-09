from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from pathlib import Path

os.environ["TASKRELAY_TOKENS"] = "writer-secret:READ_WRITE,reader-secret:READ"
os.environ["TASKRELAY_DATABASE_URL"] = "sqlite://"

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from taskrelaymcp import db, mcp_server
from taskrelaymcp.app import app
from taskrelaymcp.config import Permission
from taskrelaymcp.models import Base, Comment, Notification, Project, Status, Task
from taskrelaymcp.schemas import ProjectCreate, TaskCreate, TaskPatch
from taskrelaymcp.services import complete_task, create_project, create_task, list_tasks


def install_engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    db.engine = engine
    db.SessionLocal = sessionmaker(engine, expire_on_commit=False)
    return engine


@pytest.fixture(autouse=True)
def clean_database():
    engine = install_engine()
    db.init_db()
    yield
    engine.dispose()


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def headers(token: str = "writer-secret") -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_fresh_alembic_migration() -> None:
    engine = install_engine()
    db.init_db()
    inspector = inspect(engine)
    assert set(Base.metadata.tables) <= set(inspector.get_table_names())
    projects = {column["name"]: column for column in inspector.get_columns("projects")}
    assert projects["key"]["nullable"] is False
    assert db._affinity(str(projects["key"]["type"])) == "TEXT"
    assert {item["name"] for item in inspector.get_indexes("comments")} == {"ix_comments_task_id"}
    assert {item["name"]: item["unique"] for item in inspector.get_indexes("projects")} == {"ix_projects_key": 1}
    assert {item["name"]: item["unique"] for item in inspector.get_indexes("tags")} == {"ix_tags_name": 1}
    assert inspector.get_unique_constraints("projects") == []
    assert inspector.get_unique_constraints("tags") == []
    assert {tuple(item["constrained_columns"]) for item in inspector.get_foreign_keys("tasks")} == {
        ("target_project_id",),
        ("origin_project_id",),
    }
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0001_v01_baseline"
    with db.session_scope() as session:
        project = create_project(session, ProjectCreate(key="fresh", name="Fresh"))
        assert (
            create_task(session, TaskCreate(title="Works", target_project="fresh"), "human").target_project == project
        )
    engine.dispose()


def test_v01_adoption_preserves_rows_and_stamps_explicit_baseline(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = install_engine()
    Base.metadata.create_all(engine)
    with db.session_scope() as session:
        create_project(session, ProjectCreate(key="legacy", name="Legacy"))
    stamped: list[str] = []
    original_stamp = db.command.stamp
    monkeypatch.setattr(
        db.command, "stamp", lambda config, revision: (stamped.append(revision), original_stamp(config, revision))[1]
    )
    db.init_db()
    assert stamped == [db.V01_REVISION]
    with db.session_scope() as session:
        assert session.scalar(select(Project).where(Project.key == "legacy")).name == "Legacy"
    engine.dispose()


def test_partial_v01_schema_is_refused() -> None:
    engine = install_engine()
    Base.metadata.tables["projects"].create(engine)
    with pytest.raises(RuntimeError, match="frozen v0.1"):
        db.init_db()
    engine.dispose()


def test_malformed_complete_v01_schema_is_refused() -> None:
    engine = install_engine()
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP INDEX ix_comments_task_id")
    with pytest.raises(RuntimeError, match="frozen v0.1"):
        db.init_db()
    engine.dispose()


def test_alembic_cli_honors_database_url(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    target = tmp_path / "target.db"
    fallback = tmp_path / "ini-fallback.db"
    monkeypatch.setenv("TASKRELAY_DATABASE_URL", f"sqlite:///{target}")
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{fallback}")
    command.upgrade(config, "head")
    assert "alembic_version" in inspect(create_engine(f"sqlite:///{target}")).get_table_names()
    assert not fallback.exists()


def test_auth_and_read_only_permissions(client: TestClient) -> None:
    assert client.get("/api/projects").status_code == 401
    assert (
        client.post("/api/projects", headers=headers("reader-secret"), json={"key": "one", "name": "One"}).status_code
        == 403
    )


def test_project_summaries_hide_archived_by_default(client: TestClient) -> None:
    for key in ("active", "archived"):
        assert (
            client.post("/api/projects", headers=headers(), json={"key": key, "name": key.title()}).status_code == 201
        )
    assert client.patch("/api/projects/archived", headers=headers(), json={"archived": True}).status_code == 200
    assert [item["key"] for item in client.get("/api/projects", headers=headers()).json()] == ["active"]
    assert {item["key"] for item in client.get("/api/projects?include_archived=true", headers=headers()).json()} == {
        "active",
        "archived",
    }


def test_rest_create_and_filter_and_human_audit(client: TestClient) -> None:
    for key in ("origin", "target"):
        assert (
            client.post("/api/projects", headers=headers(), json={"key": key, "name": key.title()}).status_code == 201
        )
    created = client.post(
        "/api/tasks",
        headers=headers(),
        json={"title": "Work", "target_project": "target", "origin_project": "origin", "tags": ["review"]},
    )
    assert created.status_code == 201
    task = created.json()
    assert client.get("/api/tasks?project=target&tag=review", headers=headers()).json()[0]["title"] == "Work"
    assert (
        client.patch(f"/api/tasks/{task['id']}", headers=headers(), json={"title": "Updated"}).json()["events"][-1][
            "actor"
        ]
        == "human"
    )


def test_mcp_project_actor_and_forced_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    with db.session_scope() as session:
        create_project(session, ProjectCreate(key="home", name="Home"))
        create_project(session, ProjectCreate(key="target", name="Target"))
    monkeypatch.setattr(
        mcp_server, "get_http_headers", lambda **_: {"authorization": "Bearer writer-secret", "x-home-project": "home"}
    )
    task = mcp_server.create_task("Ship", target_project="target")
    assert task["origin_project"] == "home"
    assert task["events"][-1]["actor"] == "project:home"
    assert mcp_server.update_task(task["id"], title="Shipped")["events"][-1]["actor"] == "project:home"


def test_completed_tasks_are_immutable_and_conflicts_are_409(client: TestClient) -> None:
    assert client.post("/api/projects", headers=headers(), json={"key": "home", "name": "Home"}).status_code == 201
    task = client.post("/api/tasks", headers=headers(), json={"title": "Done", "target_project": "home"}).json()
    assert (
        client.post(f"/api/tasks/{task['id']}/complete", headers=headers(), json={"summary": "Finished"}).status_code
        == 200
    )
    assert client.patch(f"/api/tasks/{task['id']}", headers=headers(), json={"title": "Nope"}).status_code == 409
    assert client.delete(f"/api/tasks/{task['id']}", headers=headers()).status_code == 409
    assert (
        client.post(f"/api/tasks/{task['id']}/complete", headers=headers(), json={"summary": "Again"}).status_code
        == 409
    )
    assert client.patch(f"/api/tasks/{task['id']}", headers=headers(), json={"status": "TODO"}).status_code == 422


def test_completion_transaction_and_consuming_mcp_notifications(monkeypatch: pytest.MonkeyPatch) -> None:
    with db.session_scope() as session:
        create_project(session, ProjectCreate(key="home", name="Home"))
        create_project(session, ProjectCreate(key="target", name="Target"))
        task = create_task(
            session, TaskCreate(title="Ship", target_project="target"), "project:home", forced_origin="home"
        )
        complete_task(session, task, "project:home", "Evidence")
        task_id = task.id
    with db.session_scope() as session:
        assert session.scalar(select(Comment).where(Comment.task_id == task_id)).body == "Evidence"
    monkeypatch.setattr(
        mcp_server, "get_http_headers", lambda **_: {"authorization": "Bearer writer-secret", "x-home-project": "home"}
    )
    assert len(mcp_server.get_notifications()) == 1
    assert mcp_server.get_notifications() == []
    assert len(mcp_server.get_notifications(unread_only=False)) == 1
    with db.session_scope() as session:
        assert session.scalar(select(Notification.read_at)) is not None


def test_removed_surfaces_and_start_task(client: TestClient) -> None:
    assert not hasattr(mcp_server, "start_task")
    openapi = client.get("/openapi.json").json()
    assert openapi["info"]["version"] == "0.2.0"
    paths = openapi["paths"]
    assert "/api/notifications" not in paths
    assert "/api/notifications/{notification_id}" not in paths
    assert "/api/tasks/{task_id}/comments" not in paths
    assert client.get("/api/notifications", headers=headers()).status_code == 404
    assert client.patch("/api/notifications/1", headers=headers()).status_code == 405
    assert client.post("/api/tasks/1/comments", headers=headers(), json={"body": "No"}).status_code == 405
    response = client.get("/api/not-a-route", headers=headers())
    assert response.status_code == 404 and response.json() == {"detail": "Not Found"}


def test_current_writes_only_accept_todo_and_done() -> None:
    with pytest.raises(ValueError):
        TaskPatch.model_validate({"status": "TODO"})
    with pytest.raises(ValueError):
        TaskPatch.model_validate({"priority": "INVALID"})
    assert Status.TODO == "TODO"


def test_legacy_statuses_normalize_on_service_access() -> None:
    with db.session_scope() as session:
        project = create_project(session, ProjectCreate(key="home", name="Home"))
        task = Task(title="Old", status="BLOCKED", target_project=project, origin_project=project, created_by="agent")
        session.add(task)
        session.flush()
        assert list_tasks(session, project="home")[0].status == Status.TODO


def test_project_summaries_count_and_sort_by_task_activity(client: TestClient) -> None:
    for key in ("alpha", "beta", "empty"):
        assert (
            client.post("/api/projects", headers=headers(), json={"key": key, "name": key.title()}).status_code == 201
        )
    alpha = client.post("/api/tasks", headers=headers(), json={"title": "Done", "target_project": "alpha"}).json()
    client.post(f"/api/tasks/{alpha['id']}/complete", headers=headers(), json={"summary": "Finished"})
    beta = client.post("/api/tasks", headers=headers(), json={"title": "Todo", "target_project": "beta"}).json()
    with db.session_scope() as session:
        session.get(Task, alpha["id"]).updated_at = datetime(2030, 1, 1, tzinfo=UTC)
        session.get(Task, beta["id"]).updated_at = datetime(2030, 1, 2, tzinfo=UTC)
    summaries = client.get("/api/projects", headers=headers()).json()
    assert [item["key"] for item in summaries] == ["beta", "alpha", "empty"]


def test_mcp_context_separates_home_and_permission(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        mcp_server, "get_http_headers", lambda **_: {"authorization": "Bearer reader-secret", "x-home-project": "home"}
    )
    principal, home = mcp_server.context()
    assert principal.permission == Permission.READ
    assert home == "home"
    with pytest.raises(PermissionError, match="READ_WRITE"):
        mcp_server.context(write=True)


def test_mcp_exposes_agent_guide_resource() -> None:
    resource = asyncio.run(mcp_server.mcp.get_resource("taskrelay://guide"))
    assert resource is not None
    assert resource.mime_type == "text/markdown"
    guide = asyncio.run(resource.read())
    assert "X-Home-Project" in guide
    assert "get_notifications()" in guide
    assert "complete_task(task_id, summary)" in guide
