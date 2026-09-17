from __future__ import annotations

import os
import re
from asyncio import run
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from threading import Barrier

os.environ.update(
    TASKRELAY_ADMIN_USERNAME="admin",
    TASKRELAY_ADMIN_PASSWORD="bootstrap-secret-123",
    TASKRELAY_ADMIN_DISPLAY_NAME="Admin",
    TASKRELAY_SECURE_COOKIES="false",
    TASKRELAY_DATABASE_URL="sqlite://",
)

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from fastmcp.exceptions import ToolError
from sqlalchemy import ForeignKeyConstraint, UniqueConstraint, create_engine, inspect, select, text
from sqlalchemy.dialects import sqlite
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.schema import CreateIndex

from taskrelaymcp import db, mcp_server
from taskrelaymcp.app import app
from taskrelaymcp.auth import hash_secret
from taskrelaymcp.config import Principal
from taskrelaymcp.models import (
    AuditEvent,
    MCPKey,
    Note,
    NoteLink,
    NoteRevision,
    NotificationRead,
    Project,
    ProjectMembership,
    Tag,
    TagProposal,
    TagProposalStatus,
    Task,
    User,
)
from taskrelaymcp.schemas import NotePatch
from taskrelaymcp.services import Conflict, create_tag_proposal, decide_tag_proposal, patch_note

ORIGIN = {"Origin": "http://testserver"}


def _normalize_default(default: object | None) -> str | None:
    if default is None:
        return None
    value = str(getattr(default, "arg", default)).strip()
    while value.startswith("(") and value.endswith(")"):
        value = value[1:-1].strip()
    return {"true": "1", "false": "0"}.get(value.lower(), value)


def _index_signature(sql: str) -> tuple[bool, str]:
    match = re.fullmatch(
        r"CREATE\s+(UNIQUE\s+)?INDEX\s+.+?\s+ON\s+.+?\s*(\(.+?\))(?:\s+WHERE\s+(.+))?", sql, re.IGNORECASE
    )
    assert match, sql
    parts = match.group(2, 3) if match.group(3) else (match.group(2),)
    return bool(match.group(1)), re.sub(r"\s+", "", " ".join(parts)).lower()


def _assert_reflected_schema_matches_metadata(connection) -> None:
    inspector = inspect(connection)
    assert set(inspector.get_table_names()) == {*db.Base.metadata.tables, "alembic_version"}
    for table in db.Base.metadata.tables.values():
        reflected_columns = {
            column["name"]: (
                column["type"]._type_affinity.__name__,
                column["nullable"],
                _normalize_default(column["default"]),
            )
            for column in inspector.get_columns(table.name)
        }
        expected_columns = {
            column.name: (
                column.type._type_affinity.__name__,
                column.nullable,
                _normalize_default(column.server_default),
            )
            for column in table.columns
        }
        assert reflected_columns == expected_columns
        assert tuple(inspector.get_pk_constraint(table.name)["constrained_columns"]) == tuple(
            column.name for column in table.primary_key.columns
        )
        assert {tuple(constraint["column_names"]) for constraint in inspector.get_unique_constraints(table.name)} == {
            tuple(constraint.columns.keys())
            for constraint in table.constraints
            if isinstance(constraint, UniqueConstraint)
        }
        assert {
            (
                tuple(foreign_key["constrained_columns"]),
                foreign_key["referred_table"],
                tuple(foreign_key["referred_columns"]),
                foreign_key.get("options", {}).get("ondelete"),
            )
            for foreign_key in inspector.get_foreign_keys(table.name)
        } == {
            (
                tuple(constraint.column_keys),
                constraint.elements[0].column.table.name,
                tuple(element.column.name for element in constraint.elements),
                constraint.ondelete,
            )
            for constraint in table.constraints
            if isinstance(constraint, ForeignKeyConstraint)
        }
        assert {
            (index["unique"] == 1, tuple(index["column_names"])) for index in inspector.get_indexes(table.name)
        } == {
            (index.unique, tuple(column.name for column in index.columns))
            for index in table.indexes
            if tuple(index.expressions) == tuple(index.columns)
        }
        assert {
            _index_signature(sql)
            for sql in connection.execute(
                text("SELECT sql FROM sqlite_master WHERE type = 'index' AND tbl_name = :table AND sql IS NOT NULL"),
                {"table": table.name},
            ).scalars()
        } == {_index_signature(str(CreateIndex(index).compile(dialect=sqlite.dialect()))) for index in table.indexes}


def install_engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    db.engine = engine
    db.SessionLocal = sessionmaker(engine, expire_on_commit=False)
    return engine


def install_file_engine(path: Path):
    engine = db._engine(f"sqlite:///{path}")
    db.engine = engine
    db.SessionLocal = sessionmaker(engine, expire_on_commit=False)
    db.init_db()
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


def login(client: TestClient, username: str = "admin", password: str = "bootstrap-secret-123"):
    response = client.post("/api/auth/login", headers=ORIGIN, json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return response


def create_user(client: TestClient, username: str, *, admin: bool = False, password: str | None = None) -> User:
    response = client.post(
        "/api/users",
        headers=ORIGIN,
        json={
            "username": username,
            "display_name": username.title(),
            "temporary_password": password or f"temporary-{username}-123",
            "is_admin": admin,
        },
    )
    assert response.status_code == 201, response.text
    with db.session_scope() as session:
        return session.get(User, response.json()["id"])


def change_temporary_password(client: TestClient, username: str, old: str, new: str) -> None:
    login(client, username, old)
    assert client.get("/api/projects").status_code == 403
    assert (
        client.post(
            "/api/auth/password", headers=ORIGIN, json={"current_password": old, "new_password": new}
        ).status_code
        == 200
    )
    login(client, username, new)


def test_spa_serves_root_hashed_assets_without_assets_directory(client: TestClient) -> None:
    static = Path(__file__).parents[1] / "src/taskrelaymcp/static"
    assert not (static / "assets").exists()
    index = client.get("/")
    assets = list(static.glob("main-*.js"))
    if not assets:
        pytest.skip("SPA bundle missing; run `npm --prefix frontend run build`")
    asset = assets[0]
    assert index.status_code == 200 and asset.name in index.text
    assert client.get(f"/{asset.name}").status_code == 200


def test_initial_migration_round_trip_and_bootstrap(tmp_path: Path) -> None:
    engine = db._engine(f"sqlite:///{tmp_path / 'baseline.db'}")
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
        inspector = inspect(connection)
        assert set(inspector.get_table_names()) == {*db.Base.metadata.tables, "alembic_version"}
        _assert_reflected_schema_matches_metadata(connection)
        assert connection.execute(text("PRAGMA foreign_keys")).scalar() == 1
        assert any(
            item["constrained_columns"] == ["project_id", "folder_id"] for item in inspector.get_foreign_keys("notes")
        )
        command.downgrade(config, "base")
        assert set(inspect(connection).get_table_names()) == {"alembic_version"}
        command.upgrade(config, "head")
    db.engine = engine
    db.SessionLocal = sessionmaker(engine, expire_on_commit=False)
    db.init_db()
    with db.session_scope() as session:
        assert session.scalar(select(User).where(User.username == "admin")).is_admin
    engine.dispose()


def test_notes_migration_rejects_cross_project_folder_assignment(tmp_path: Path) -> None:
    engine = install_file_engine(tmp_path / "notes.db")
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO projects (key,name,description,color,archived,tasks_enabled,notes_enabled,created_at) "
                "VALUES ('one','One','',NULL,0,1,1,CURRENT_TIMESTAMP), "
                "('two','Two','',NULL,0,1,1,CURRENT_TIMESTAMP)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO note_folders (project_id,parent_id,name,created_by_user_id,created_at) "
                "VALUES (2,NULL,'Other',1,CURRENT_TIMESTAMP)"
            )
        )
        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    "INSERT INTO notes (project_id,folder_id,title,markdown,version,created_by_user_id,"
                    "updated_by_user_id,created_at,updated_at,archived_at) "
                    "VALUES (1,1,'Cross','',1,1,1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,NULL)"
                )
            )
    engine.dispose()


def test_note_patch_compares_version_once_and_records_one_predecessor(tmp_path: Path) -> None:
    engine = install_file_engine(tmp_path / "notes.db")
    with db.session_scope() as session:
        user = session.scalar(select(User).where(User.username == "admin"))
        project = Project(key="notes", name="Notes", notes_enabled=True)
        session.add(project)
        session.flush()
        session.add(ProjectMembership(project_id=project.id, user_id=user.id, role="OWNER"))
        note = Note(
            project_id=project.id,
            title="Race",
            markdown="before",
            created_by_user_id=user.id,
            updated_by_user_id=user.id,
        )
        session.add(note)
        session.flush()
        note_id = note.id
        principal = Principal(user.id, user.username, True, "WEB")
    barrier = Barrier(2)

    def patch() -> str:
        with db.session_scope() as session:
            note = session.get(Note, note_id)
            barrier.wait()
            try:
                patch_note(session, note, NotePatch(markdown="after", expected_version=1), principal)
            except Conflict:
                return "conflict"
            return "winner"

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(lambda _: patch(), range(2))) == ["conflict", "winner"]
    with db.session_scope() as session:
        assert session.get(Note, note_id).version == 2
        revisions = list(session.scalars(select(NoteRevision).where(NoteRevision.note_id == note_id)))
        assert [(revision.version, revision.markdown) for revision in revisions] == [(1, "before")]
    engine.dispose()


def test_note_patch_replaces_outgoing_links_and_backlinks(tmp_path: Path) -> None:
    engine = install_file_engine(tmp_path / "notes.db")
    with db.session_scope() as session:
        user = session.scalar(select(User).where(User.username == "admin"))
        project = Project(key="notes", name="Notes", notes_enabled=True)
        session.add(project)
        session.flush()
        session.add(ProjectMembership(project_id=project.id, user_id=user.id, role="OWNER"))
        old_target = Note(
            project_id=project.id,
            title="Old",
            markdown="",
            created_by_user_id=user.id,
            updated_by_user_id=user.id,
        )
        new_target = Note(
            project_id=project.id,
            title="New",
            markdown="",
            created_by_user_id=user.id,
            updated_by_user_id=user.id,
        )
        session.add_all((old_target, new_target))
        session.flush()
        source = Note(
            project_id=project.id,
            title="Source",
            markdown=f"[[N-{old_target.id}]]",
            created_by_user_id=user.id,
            updated_by_user_id=user.id,
        )
        session.add(source)
        session.flush()
        session.add(NoteLink(source_note_id=source.id, target_note_id=old_target.id))
        source_id, old_target_id, new_target_id = source.id, old_target.id, new_target.id
        principal = Principal(user.id, user.username, True, "WEB")
    with db.session_scope() as session:
        source = session.get(Note, source_id)
        patch_note(session, source, NotePatch(markdown=f"[[N-{new_target_id}]]", expected_version=1), principal)
    with db.session_scope() as session:
        links = list(session.scalars(select(NoteLink).where(NoteLink.source_note_id == source_id)))
        assert [(link.source_note_id, link.target_note_id) for link in links] == [(source_id, new_target_id)]
        assert not session.scalar(select(NoteLink).where(NoteLink.target_note_id == old_target_id))
        assert (
            session.scalar(select(NoteLink).where(NoteLink.target_note_id == new_target_id)).source_note_id == source_id
        )
    engine.dispose()


def test_login_cookie_logout_and_mandatory_password_change(client: TestClient) -> None:
    assert client.get("/api/auth/me").status_code == 401
    assert (
        client.post("/api/auth/login", json={"username": "admin", "password": "bootstrap-secret-123"}).status_code
        == 403
    )
    login(client)
    assert (
        "HttpOnly"
        in client.post(
            "/api/auth/login", headers=ORIGIN, json={"username": "admin", "password": "bootstrap-secret-123"}
        ).headers["set-cookie"]
    )
    create_user(client, "alice")
    client.cookies.clear()
    change_temporary_password(client, "alice", "temporary-alice-123", "alice-new-password-123")
    assert client.post("/api/auth/logout", headers=ORIGIN).status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_public_origin_supports_tls_proxy_and_requires_configuration_in_production(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TASKRELAY_PUBLIC_ORIGIN", "https://tasks.example.com")
    https_origin = {"Origin": "https://tasks.example.com"}
    assert (
        client.post(
            "/api/auth/login", headers=https_origin, json={"username": "admin", "password": "bootstrap-secret-123"}
        ).status_code
        == 200
    )
    assert client.post("/api/projects", headers=https_origin, json={"key": "tls", "name": "TLS"}).status_code == 201
    assert (
        client.post(
            "/api/projects", headers={"Origin": "https://other.example.com"}, json={"key": "bad", "name": "Bad"}
        ).status_code
        == 403
    )
    monkeypatch.delenv("TASKRELAY_PUBLIC_ORIGIN")
    monkeypatch.setenv("TASKRELAY_SECURE_COOKIES", "true")
    assert client.post("/api/projects", headers=ORIGIN, json={"key": "missing", "name": "Missing"}).status_code == 503


def test_admin_lifecycle_and_owner_final_admin_guards(client: TestClient) -> None:
    login(client)
    alice = create_user(client, "alice", admin=True)
    project = client.post("/api/projects", headers=ORIGIN, json={"key": "one", "name": "One"})
    assert project.status_code == 201
    assert client.post(f"/api/users/{alice.id}/deactivate", headers=ORIGIN).status_code == 204
    assert client.post("/api/users/1/deactivate", headers=ORIGIN).status_code == 409  # final active admin and owner
    bob = create_user(client, "bob", admin=True)
    assert client.post("/api/users/1/deactivate", headers=ORIGIN).status_code == 409  # project owner
    assert (
        client.post(
            f"/api/users/{bob.id}/reset-password", headers=ORIGIN, json={"temporary_password": "reset-password-123"}
        ).status_code
        == 204
    )


def test_membership_visibility_writes_transfer_and_assignee(client: TestClient) -> None:
    login(client)
    create_user(client, "alice")
    client.cookies.clear()
    change_temporary_password(client, "alice", "temporary-alice-123", "alice-new-password-123")
    assert client.get("/api/projects").json() == []
    client.cookies.clear()
    login(client)
    assert client.post("/api/projects", headers=ORIGIN, json={"key": "one", "name": "One"}).status_code == 201
    assert (
        client.post(
            "/api/tasks", headers=ORIGIN, json={"title": "bad", "target_project": "one", "assigned_user": "alice"}
        ).status_code
        == 409
    )
    assert client.post("/api/projects/one/members", headers=ORIGIN, json={"username": "alice"}).status_code == 201
    task = client.post(
        "/api/tasks", headers=ORIGIN, json={"title": "ok", "target_project": "one", "assigned_user": "alice"}
    )
    assert task.status_code == 201 and task.json()["assignee"] == "Alice"
    assert (
        client.post("/api/projects/one/transfer-owner", headers=ORIGIN, json={"username": "alice"}).status_code == 204
    )
    assert client.delete("/api/projects/one/members/alice", headers=ORIGIN).status_code == 404
    client.cookies.clear()
    login(client, "alice", "alice-new-password-123")
    assert client.delete("/api/projects/one/members/admin", headers=ORIGIN).status_code == 204


def test_member_removal_requires_reassigning_todo_tasks(client: TestClient) -> None:
    login(client)
    create_user(client, "alice")
    assert client.post("/api/projects", headers=ORIGIN, json={"key": "one", "name": "One"}).status_code == 201
    assert client.post("/api/projects/one/members", headers=ORIGIN, json={"username": "alice"}).status_code == 201
    task = client.post(
        "/api/tasks", headers=ORIGIN, json={"title": "assigned", "target_project": "one", "assigned_user": "alice"}
    ).json()
    assert client.delete("/api/projects/one/members/alice", headers=ORIGIN).status_code == 409
    assert client.post(f"/api/tasks/{task['id']}/complete", headers=ORIGIN, json={"summary": "done"}).status_code == 200
    assert client.delete("/api/projects/one/members/alice", headers=ORIGIN).status_code == 204


def test_cross_project_requires_dual_membership_and_admin_inspection_is_read_only(client: TestClient) -> None:
    login(client)
    create_user(client, "alice")
    for key in ("origin", "target"):
        client.post("/api/projects", headers=ORIGIN, json={"key": key, "name": key.title()})
    client.post("/api/projects/origin/members", headers=ORIGIN, json={"username": "alice"})
    client.cookies.clear()
    change_temporary_password(client, "alice", "temporary-alice-123", "alice-new-password-123")
    assert (
        client.post(
            "/api/tasks",
            headers=ORIGIN,
            json={"title": "cross", "origin_project": "origin", "target_project": "target"},
        ).status_code
        == 404
    )
    client.cookies.clear()
    login(client)
    client.post("/api/projects/target/members", headers=ORIGIN, json={"username": "alice"})
    client.cookies.clear()
    login(client, "alice", "alice-new-password-123")
    assert (
        client.post(
            "/api/tasks",
            headers=ORIGIN,
            json={"title": "cross", "origin_project": "origin", "target_project": "target"},
        ).status_code
        == 201
    )
    private = client.post("/api/projects", headers=ORIGIN, json={"key": "alice", "name": "Alice"})
    assert private.status_code == 201
    private_task = client.post(
        "/api/tasks", headers=ORIGIN, json={"title": "private", "target_project": "alice"}
    ).json()
    client.cookies.clear()
    login(client)
    summaries = client.get("/api/projects").json()
    assert "alice" not in {item["key"] for item in summaries}
    assert all("private" not in str(item) for item in summaries)
    assert "alice" in {item["key"] for item in client.get("/api/projects?inspection=true").json()}
    assert client.get(f"/api/tasks/{private_task['id']}?inspection=true").status_code == 200
    assert client.patch(f"/api/tasks/{private_task['id']}", headers=ORIGIN, json={"title": "No"}).status_code == 404
    assert client.patch("/api/projects/alice", headers=ORIGIN, json={"name": "No"}).status_code == 404
    with db.session_scope() as session:
        assert session.scalar(select(AuditEvent).where(AuditEvent.action == "INSPECTION_READ"))


def test_inspection_marker_rejects_writes_even_to_member_projects(client: TestClient) -> None:
    login(client)
    assert client.post("/api/projects", headers=ORIGIN, json={"key": "one", "name": "One"}).status_code == 201
    inspection_headers = ORIGIN | {"X-TaskRelay-Inspection": "true"}
    assert client.patch("/api/projects/one", headers=inspection_headers, json={"name": "Blocked"}).status_code == 403
    assert client.patch("/api/projects/one", headers=ORIGIN, json={"name": "Allowed"}).status_code == 200


def test_project_summary_includes_actionable_task_note_and_activity_metadata(client: TestClient) -> None:
    login(client)
    create_user(client, "alice")
    assert (
        client.post(
            "/api/projects", headers=ORIGIN, json={"key": "summary", "name": "Summary", "notes_enabled": True}
        ).status_code
        == 201
    )
    assert client.post("/api/projects/summary/members", headers=ORIGIN, json={"username": "alice"}).status_code == 201
    root = client.post("/api/projects/summary/note-folders", headers=ORIGIN, json={"name": "Root"}).json()
    child = client.post(
        "/api/projects/summary/note-folders", headers=ORIGIN, json={"name": "Child", "parent_id": root["id"]}
    ).json()
    note = client.post(
        "/api/projects/summary/notes", headers=ORIGIN, json={"title": "Plan", "markdown": "", "folder_id": child["id"]}
    ).json()
    summary = next(item for item in client.get("/api/projects").json() if item["key"] == "summary")
    assert summary["recent_note"] == {
        "id": note["id"],
        "title": "Plan",
        "updated_at": summary["recent_note"]["updated_at"],
        "updater": "Admin",
        "folder_path": "Root / Child",
    }
    assert summary["latest_activity"] | {"created_at": None} == {
        "action": "NOTE_CREATED",
        "object_type": "NOTE",
        "object_id": note["id"],
        "object_title": "Plan",
        "actor": "Admin",
        "created_at": None,
    }
    task = client.post(
        "/api/tasks",
        headers=ORIGIN,
        json={"title": "Ship", "target_project": "summary", "assigned_user": "alice", "priority": "HIGH"},
    ).json()
    summary = next(item for item in client.get("/api/projects").json() if item["key"] == "summary")
    assert summary["todo_preview"] == [
        {
            "id": task["id"],
            "title": "Ship",
            "priority": "HIGH",
            "assignee": "Alice",
            "updated_at": summary["todo_preview"][0]["updated_at"],
        }
    ]
    assert summary["latest_activity"] | {"created_at": None} == {
        "action": "CREATED",
        "object_type": "TASK",
        "object_id": task["id"],
        "object_title": "Ship",
        "actor": "Admin",
        "created_at": None,
    }


def test_project_summary_uses_archived_latest_note_for_activity_and_note_ordering(client: TestClient) -> None:
    login(client)
    for key in ("older", "newer"):
        assert (
            client.post(
                "/api/projects", headers=ORIGIN, json={"key": key, "name": key.title(), "notes_enabled": True}
            ).status_code
            == 201
        )
    visible = client.post("/api/projects/older/notes", headers=ORIGIN, json={"title": "Visible", "markdown": ""}).json()
    archived = client.post(
        "/api/projects/older/notes", headers=ORIGIN, json={"title": "Archived", "markdown": ""}
    ).json()
    assert (
        client.patch(
            f"/api/notes/{archived['id']}", headers=ORIGIN, json={"archived": True, "expected_version": 1}
        ).status_code
        == 200
    )
    summaries = client.get("/api/projects").json()
    older = next(item for item in summaries if item["key"] == "older")
    assert [item["key"] for item in summaries[:2]] == ["older", "newer"]
    assert older["recent_note"]["id"] == visible["id"]
    assert older["latest_activity"] | {"created_at": None} == {
        "action": "NOTE_UPDATED",
        "object_type": "NOTE",
        "object_id": archived["id"],
        "object_title": "Archived",
        "actor": "Admin",
        "created_at": None,
    }


def test_mcp_key_use_revoke_attribution_and_no_get_search_count_leak(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    login(client)
    create_user(client, "alice")
    for key in ("home", "secret"):
        client.post("/api/projects", headers=ORIGIN, json={"key": key, "name": key.title()})
    client.post("/api/projects/home/members", headers=ORIGIN, json={"username": "alice"})
    hidden_tag = client.post(
        "/api/projects/secret/tags", headers=ORIGIN, json={"name": "hidden-tag", "color": "#112233"}
    ).json()
    hidden = client.post(
        "/api/tasks",
        headers=ORIGIN,
        json={"title": "needle hidden", "target_project": "secret", "tag_ids": [hidden_tag["id"]]},
    ).json()
    client.cookies.clear()
    change_temporary_password(client, "alice", "temporary-alice-123", "alice-new-password-123")
    created_key = client.post("/api/mcp-keys", headers=ORIGIN, json={"name": "laptop"}).json()
    assert created_key["secret"].startswith("trm_") and "secret" not in client.get("/api/mcp-keys").json()[0]
    monkeypatch.setattr(
        mcp_server,
        "get_http_headers",
        lambda **_: {"authorization": f"Bearer {created_key['secret']}", "x-home-project": "home"},
    )
    task = mcp_server.create_task("visible needle")
    assert task["events"][-1]["channel"] == "MCP" and task["events"][-1]["mcp_key"] == "laptop"
    assert mcp_server.search_tasks("needle")[0]["id"] == task["id"]
    assert all(tag["name"] != "hidden-tag" for tag in client.get("/api/tags").json())
    with pytest.raises(ValueError):
        mcp_server.get_task(hidden["id"])
    assert mcp_server.workspace_status()["projects"] == 1
    assert client.delete(f"/api/mcp-keys/{created_key['id']}", headers=ORIGIN).status_code == 204
    with pytest.raises(PermissionError):
        mcp_server.context()
    with db.session_scope() as session:
        assert session.scalar(select(MCPKey.secret_hash)) == hash_secret(created_key["secret"])


def test_mcp_home_project_errors_do_not_reveal_project_existence(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    login(client)
    create_user(client, "alice")
    assert client.post("/api/projects", headers=ORIGIN, json={"key": "private", "name": "Private"}).status_code == 201
    client.cookies.clear()
    change_temporary_password(client, "alice", "temporary-alice-123", "alice-new-password-123")
    secret = client.post("/api/mcp-keys", headers=ORIGIN, json={"name": "alice-key"}).json()["secret"]
    errors = []
    for home in ("missing", "private"):
        monkeypatch.setattr(
            mcp_server,
            "get_http_headers",
            lambda home=home, **_: {"authorization": f"Bearer {secret}", "x-home-project": home},
        )
        with pytest.raises(PermissionError) as exc:
            mcp_server.context()
        errors.append(str(exc.value))
    assert errors == ["Home project not found", "Home project not found"]


def test_project_tags_and_proposal_approval(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    login(client)
    create_user(client, "alice")
    for key in ("one", "two"):
        assert client.post("/api/projects", headers=ORIGIN, json={"key": key, "name": key.title()}).status_code == 201
    assert client.post("/api/projects/one/members", headers=ORIGIN, json={"username": "alice"}).status_code == 201
    tag = client.post(
        "/api/projects/one/tags", headers=ORIGIN, json={"name": "urgent", "color": "#112233", "description": " now "}
    )
    active = client.post("/api/projects/one/tags", headers=ORIGIN, json={"name": "active", "color": "#445566"}).json()
    replacement = client.post(
        "/api/projects/two/tags", headers=ORIGIN, json={"name": "replacement", "color": "#778899"}
    ).json()
    assert tag.status_code == 201 and tag.json()["description"] == "now"
    task = client.post(
        "/api/tasks", headers=ORIGIN, json={"title": "tagged", "target_project": "one", "tag_ids": [tag.json()["id"]]}
    )
    assert task.status_code == 201 and task.json()["tags"][0]["name"] == "urgent"
    assert (
        client.post(
            "/api/tasks",
            headers=ORIGIN,
            json={"title": "wrong", "target_project": "two", "tag_ids": [tag.json()["id"]]},
        ).status_code
        == 409
    )
    assert client.post(f"/api/tags/{tag.json()['id']}/archive", headers=ORIGIN).status_code == 200
    assert (
        client.patch(
            f"/api/tasks/{task.json()['id']}", headers=ORIGIN, json={"tag_ids": [tag.json()["id"], active["id"]]}
        ).status_code
        == 200
    )
    assert (
        client.patch(
            f"/api/tasks/{task.json()['id']}", headers=ORIGIN, json={"tag_ids": [tag.json()["id"]]}
        ).status_code
        == 200
    )
    assert [item["id"] for item in client.get(f"/api/tasks/{task.json()['id']}").json()["tags"]] == [tag.json()["id"]]
    assert client.patch(f"/api/tasks/{task.json()['id']}", headers=ORIGIN, json={"tag_ids": []}).status_code == 200
    assert (
        client.patch(
            f"/api/tasks/{task.json()['id']}", headers=ORIGIN, json={"tag_ids": [tag.json()["id"]]}
        ).status_code
        == 409
    )
    assert (
        client.post(
            "/api/tasks",
            headers=ORIGIN,
            json={"title": "new archived", "target_project": "one", "tag_ids": [tag.json()["id"]]},
        ).status_code
        == 409
    )
    assert (
        client.patch(
            f"/api/tasks/{task.json()['id']}",
            headers=ORIGIN,
            json={"target_project": "two", "tag_ids": [tag.json()["id"], replacement["id"]]},
        ).status_code
        == 409
    )
    secret = client.post("/api/mcp-keys", headers=ORIGIN, json={"name": "proposal-key"}).json()["secret"]
    monkeypatch.setattr(
        mcp_server,
        "get_http_headers",
        lambda **_: {"authorization": f"Bearer {secret}", "x-home-project": "one"},
    )
    proposal = mcp_server.propose_project_tag("review", "#445566", apply_to_task_ids=[task.json()["id"]])
    assert proposal["status"] == "PENDING"
    approved = client.post(f"/api/tag-proposals/{proposal['id']}/approve", headers=ORIGIN, json={"color": "#778899"})
    assert approved.status_code == 200 and approved.json()["status"] == "APPROVED"
    assert client.get(f"/api/tasks/{task.json()['id']}").json()["tags"][-1]["name"] == "review"


def test_task_tag_project_constraint_rejects_sql_and_allows_replacement_move(client: TestClient) -> None:
    login(client)
    for key in ("one", "two"):
        assert client.post("/api/projects", headers=ORIGIN, json={"key": key, "name": key.title()}).status_code == 201
    one_tag = client.post("/api/projects/one/tags", headers=ORIGIN, json={"name": "one", "color": "#112233"}).json()
    two_tag = client.post("/api/projects/two/tags", headers=ORIGIN, json={"name": "two", "color": "#112233"}).json()
    task = client.post(
        "/api/tasks", headers=ORIGIN, json={"title": "move", "target_project": "one", "tag_ids": [one_tag["id"]]}
    ).json()
    assert (
        client.patch(
            f"/api/tasks/{task['id']}", headers=ORIGIN, json={"target_project": "two", "tag_ids": [two_tag["id"]]}
        ).status_code
        == 200
    )
    with db.engine.begin() as connection, pytest.raises(IntegrityError):
        connection.execute(text("PRAGMA foreign_keys=ON"))
        connection.execute(
            text("INSERT INTO task_tags (task_id, tag_id, project_id) VALUES (:task, :tag, :project)"),
            {"task": task["id"], "tag": one_tag["id"], "project": 2},
        )


def test_tag_proposals_reject_archived_names_expire_and_revalidate_tasks(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    login(client)
    for key in ("one", "two"):
        assert client.post("/api/projects", headers=ORIGIN, json={"key": key, "name": key.title()}).status_code == 201
    archived = client.post("/api/projects/one/tags", headers=ORIGIN, json={"name": "old", "color": "#112233"}).json()
    assert client.post(f"/api/tags/{archived['id']}/archive", headers=ORIGIN).status_code == 200
    task = client.post("/api/tasks", headers=ORIGIN, json={"title": "todo", "target_project": "one"}).json()
    secret = client.post("/api/mcp-keys", headers=ORIGIN, json={"name": "proposal"}).json()["secret"]
    monkeypatch.setattr(
        mcp_server,
        "get_http_headers",
        lambda **_: {"authorization": f"Bearer {secret}", "x-home-project": "one"},
    )
    archived_proposal = mcp_server.propose_project_tag("old", "#112233", apply_to_task_ids=[task["id"]])
    assert (
        client.post(f"/api/tag-proposals/{archived_proposal['id']}/approve", headers=ORIGIN, json={}).status_code == 409
    )
    assert client.get("/api/tag-proposals").json()[0]["status"] == "PENDING"
    second_task = client.post("/api/tasks", headers=ORIGIN, json={"title": "second", "target_project": "one"}).json()
    merged = mcp_server.propose_project_tag("merge", "#112233", apply_to_task_ids=[task["id"]])
    merged_again = mcp_server.propose_project_tag("merge", "#445566", apply_to_task_ids=[second_task["id"]])
    assert merged_again["id"] == merged["id"]
    assert merged_again["task_ids"] == [task["id"], second_task["id"]]
    no_apply = mcp_server.propose_project_tag("no-apply", "#112233", apply_to_task_ids=[second_task["id"]])
    approved = client.post(
        f"/api/tag-proposals/{no_apply['id']}/approve", headers=ORIGIN, json={"apply_requested_tasks": False}
    ).json()
    assert (
        client.post(
            f"/api/tag-proposals/{no_apply['id']}/approve", headers=ORIGIN, json={"apply_requested_tasks": False}
        ).json()["resolved_tag_id"]
        == approved["resolved_tag_id"]
    )
    assert not client.get(f"/api/tasks/{second_task['id']}").json()["tags"]
    missing_task = client.post("/api/tasks", headers=ORIGIN, json={"title": "missing", "target_project": "one"}).json()
    missing = mcp_server.propose_project_tag("missing", "#112233", apply_to_task_ids=[missing_task["id"]])
    assert client.delete(f"/api/tasks/{missing_task['id']}", headers=ORIGIN).status_code == 204
    assert client.post(f"/api/tag-proposals/{missing['id']}/approve", headers=ORIGIN, json={}).status_code == 409
    invalid = mcp_server.propose_project_tag("invalid", "#112233", apply_to_task_ids=[task["id"]])
    assert client.post(f"/api/tasks/{task['id']}/complete", headers=ORIGIN, json={"summary": "done"}).status_code == 200
    assert client.post(f"/api/tag-proposals/{invalid['id']}/approve", headers=ORIGIN, json={}).status_code == 409
    with db.session_scope() as session:
        assert session.get(TagProposal, invalid["id"]).status == TagProposalStatus.PENDING
        assert not session.scalar(select(Tag).where(Tag.name == "invalid"))
        expired = TagProposal(
            project_id=1,
            proposed_by_user_id=1,
            mcp_key_id=1,
            name="expired",
            color="#112233",
            expires_at=datetime.now(UTC),
        )
        session.add(expired)
        session.flush()
        expired_id = expired.id
    assert (
        client.post(f"/api/tag-proposals/{expired_id}/approve", headers=ORIGIN, json={}).json()["status"] == "EXPIRED"
    )


def test_tag_acl_description_and_mcp_tag_probing_are_normalized(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    login(client)
    create_user(client, "alice")
    for key in ("shared", "private"):
        assert client.post("/api/projects", headers=ORIGIN, json={"key": key, "name": key.title()}).status_code == 201
    assert client.post("/api/projects/shared/members", headers=ORIGIN, json={"username": "alice"}).status_code == 201
    tag = client.post(
        "/api/projects/shared/tags",
        headers=ORIGIN,
        json={"name": "mixed", "color": "#112233", "description": " Keep CASE "},
    ).json()
    private_tag = client.post(
        "/api/projects/private/tags", headers=ORIGIN, json={"name": "secret", "color": "#112233"}
    ).json()
    assert tag["description"] == "Keep CASE"
    client.cookies.clear()
    change_temporary_password(client, "alice", "temporary-alice-123", "alice-new-password-123")
    response = client.patch(f"/api/tags/{tag['id']}", headers=ORIGIN, json={"description": " More CASE "})
    assert response.json()["description"] == "More CASE"
    assert client.patch(f"/api/tags/{tag['id']}", headers=ORIGIN, json={"name": "renamed"}).status_code == 404
    assert client.post(f"/api/tags/{tag['id']}/archive", headers=ORIGIN).status_code == 404
    assert client.patch(f"/api/tags/{private_tag['id']}", headers=ORIGIN, json={"description": "x"}).json() == {
        "detail": "Tag not found"
    }
    secret = client.post("/api/mcp-keys", headers=ORIGIN, json={"name": "alice"}).json()["secret"]
    monkeypatch.setattr(
        mcp_server,
        "get_http_headers",
        lambda **_: {"authorization": f"Bearer {secret}", "x-home-project": "shared"},
    )
    errors = []
    with db.session_scope() as session:
        for project in ("private", "missing"):
            with pytest.raises(ValueError) as exc:
                mcp_server._tag_ids(session, project, ["secret"], Principal(2, "alice", False, "MCP", 1))
            errors.append(str(exc.value))
    assert errors == ["Target project not found", "Target project not found"]


def test_concurrent_tag_proposal_creation_and_approval_have_one_winner(tmp_path: Path) -> None:
    engine = install_file_engine(tmp_path / "proposals.db")
    with db.session_scope() as session:
        user = session.scalar(select(User).where(User.username == "admin"))
        project = Project(key="one", name="One")
        session.add(project)
        session.flush()
        session.add(ProjectMembership(project_id=project.id, user_id=user.id, role="OWNER"))
        key = MCPKey(user_id=user.id, name="proposal", secret_hash="proposal")
        session.add(key)
        tasks = [
            Task(title=title, target_project_id=project.id, origin_project_id=project.id, created_by=user.username)
            for title in ("one", "two")
        ]
        session.add_all(tasks)
        session.flush()
        project_id, task_ids = project.id, [task.id for task in tasks]
        principal = Principal(user.id, user.username, True, "MCP", key.id, key.name)
    barrier = Barrier(2)

    def create(task_id: int) -> int:
        with db.session_scope() as session:
            barrier.wait()
            proposal = create_tag_proposal(
                session,
                session.get(Project, project_id),
                "merge",
                "#112233",
                "",
                [task_id],
                principal,
            )
            return proposal.id

    with ThreadPoolExecutor(max_workers=2) as executor:
        proposal_ids = list(executor.map(create, task_ids))
    assert len(set(proposal_ids)) == 1
    proposal_id = proposal_ids[0]
    barrier = Barrier(2)

    def approve() -> tuple[str, int]:
        with db.session_scope() as session:
            proposal = session.get(TagProposal, proposal_id)
            barrier.wait()
            decided = decide_tag_proposal(session, proposal, principal, True)
            return decided.status, decided.resolved_tag_id

    with ThreadPoolExecutor(max_workers=2) as executor:
        decisions = list(executor.map(lambda _: approve(), range(2)))
    assert decisions[0] == decisions[1]
    with db.session_scope() as session:
        proposal = session.get(TagProposal, proposal_id)
        assert proposal.status == TagProposalStatus.APPROVED
        assert {task.id for task in proposal.tasks} == set(task_ids)
        assert session.scalar(select(Tag).where(Tag.name == "merge"))
        assert all([tag.name for tag in session.get(Task, task_id).tags] == ["merge"] for task_id in task_ids)
    engine.dispose()


def test_mcp_project_tag_elicitation_outcomes(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    login(client)
    assert client.post("/api/projects", headers=ORIGIN, json={"key": "home", "name": "Home"}).status_code == 201
    secret = client.post("/api/mcp-keys", headers=ORIGIN, json={"name": "elicitation-key"}).json()["secret"]
    monkeypatch.setattr(
        mcp_server,
        "get_http_headers",
        lambda **_: {"authorization": f"Bearer {secret}", "x-home-project": "home"},
    )

    class Elicitation:
        def __init__(self, action: str, data: bool | None = None):
            self.action, self.data = action, data

    class Context:
        def __init__(self, result):
            self.result = result

        async def elicit(self, *args, **kwargs):
            if isinstance(self.result, Exception):
                raise self.result
            return self.result

    assert (
        run(mcp_server.create_project_tag("accepted", "#112233", Context(Elicitation("accept", True))))["status"]
        == "CREATED"
    )
    assert run(mcp_server.create_project_tag("declined", "#112233", Context(Elicitation("decline")))) == {
        "status": "DECLINED"
    }
    assert run(mcp_server.create_project_tag("cancelled", "#112233", Context(Elicitation("cancel")))) == {
        "status": "CANCELLED"
    }
    assert run(
        mcp_server.create_project_tag("unsupported", "#112233", Context(ToolError("Elicitation is not supported")))
    ) == {"status": "ELICITATION_UNSUPPORTED", "fallback_tool": "propose_project_tag"}
    with pytest.raises(ToolError, match="unexpected"):
        run(mcp_server.create_project_tag("error", "#112233", Context(ToolError("unexpected"))))
    assert {tag["name"] for tag in client.get("/api/tags").json()} == {"accepted"}


def test_notifications_are_consumed_per_user(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    login(client)
    create_user(client, "alice")
    for key in ("home", "target"):
        client.post("/api/projects", headers=ORIGIN, json={"key": key, "name": key.title()})
        client.post(f"/api/projects/{key}/members", headers=ORIGIN, json={"username": "alice"})
    admin_key = client.post("/api/mcp-keys", headers=ORIGIN, json={"name": "admin-key"}).json()["secret"]
    task = client.post(
        "/api/tasks", headers=ORIGIN, json={"title": "cross", "origin_project": "home", "target_project": "target"}
    ).json()
    client.post(f"/api/tasks/{task['id']}/complete", headers=ORIGIN, json={"summary": "done"})
    client.cookies.clear()
    change_temporary_password(client, "alice", "temporary-alice-123", "alice-new-password-123")
    alice_key = client.post("/api/mcp-keys", headers=ORIGIN, json={"name": "alice-key"}).json()["secret"]
    for secret in (admin_key, alice_key):
        monkeypatch.setattr(
            mcp_server,
            "get_http_headers",
            lambda secret=secret, **_: {"authorization": f"Bearer {secret}", "x-home-project": "home"},
        )
        assert len(mcp_server.get_notifications()) == 1
        assert mcp_server.get_notifications() == []
    with db.session_scope() as session:
        assert len(list(session.scalars(select(NotificationRead)))) == 2


def test_competing_notification_claims_deliver_once(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'claims.db'}", connect_args={"check_same_thread": False})
    db.engine = engine
    db.SessionLocal = sessionmaker(engine, expire_on_commit=False)
    db.init_db()
    login(client)
    for key in ("home", "target"):
        assert client.post("/api/projects", headers=ORIGIN, json={"key": key, "name": key.title()}).status_code == 201
    secret = client.post("/api/mcp-keys", headers=ORIGIN, json={"name": "admin-key"}).json()["secret"]
    task = client.post(
        "/api/tasks",
        headers=ORIGIN,
        json={"title": "notification", "origin_project": "home", "target_project": "target"},
    ).json()
    assert client.post(f"/api/tasks/{task['id']}/complete", headers=ORIGIN, json={"summary": "done"}).status_code == 200
    monkeypatch.setattr(
        mcp_server,
        "get_http_headers",
        lambda **_: {"authorization": f"Bearer {secret}", "x-home-project": "home"},
    )
    principal_home = mcp_server.context()
    barrier = Barrier(2)
    monkeypatch.setattr(mcp_server, "context", lambda: (barrier.wait(), principal_home)[1])

    with ThreadPoolExecutor(max_workers=2) as executor:
        claims = list(executor.map(lambda _: mcp_server.get_notifications(), range(2)))

    assert sorted(len(claim) for claim in claims) == [0, 1]
    monkeypatch.setattr(mcp_server, "context", lambda: principal_home)
    assert mcp_server.get_notifications() == []
    with db.session_scope() as session:
        assert len(list(session.scalars(select(NotificationRead)))) == 1
    engine.dispose()


def test_project_notes_folders_revisions_links_and_capabilities(client: TestClient) -> None:
    login(client)
    assert (
        client.post(
            "/api/projects",
            headers=ORIGIN,
            json={"key": "notes", "name": "Notes", "tasks_enabled": False, "notes_enabled": True},
        ).status_code
        == 201
    )
    folder = client.post("/api/projects/notes/note-folders", headers=ORIGIN, json={"name": " Docs "}).json()
    assert folder["name"] == "Docs"
    note = client.post(
        "/api/projects/notes/notes",
        headers=ORIGIN,
        json={"title": " One ", "markdown": "first", "folder_id": folder["id"]},
    ).json()
    linked = client.post(
        "/api/projects/notes/notes", headers=ORIGIN, json={"title": "Two", "markdown": f"[[N-{note['id']}]]"}
    ).json()
    assert len(client.get("/api/projects/notes/notes?limit=1").json()) == 1
    assert client.get("/api/projects/notes/notes?limit=0").status_code == 422
    detail = client.get(f"/api/notes/{note['id']}").json()
    assert detail["title"] == "One" and detail["backlinks"] == [{"id": linked["id"], "title": "Two"}]
    changed = client.patch(
        f"/api/notes/{note['id']}", headers=ORIGIN, json={"markdown": "second", "expected_version": 1}
    )
    assert changed.status_code == 200 and changed.json()["version"] == 2
    assert (
        client.patch(
            f"/api/notes/{note['id']}", headers=ORIGIN, json={"archived": True, "expected_version": 1}
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"/api/notes/{note['id']}/revisions/1/restore", headers=ORIGIN, json={"expected_version": 2}
        ).json()["version"]
        == 3
    )
    assert [item["version"] for item in client.get(f"/api/notes/{note['id']}/revisions").json()] == [2, 1]
    assert client.delete(f"/api/note-folders/{folder['id']}", headers=ORIGIN).status_code == 409
    assert client.patch("/api/projects/notes", headers=ORIGIN, json={"notes_enabled": False}).status_code == 409


def test_note_folder_and_title_constraints_reject_cross_project_parent_and_cycles(client: TestClient) -> None:
    login(client)
    for key in ("one", "two"):
        assert (
            client.post(
                "/api/projects", headers=ORIGIN, json={"key": key, "name": key.title(), "notes_enabled": True}
            ).status_code
            == 201
        )
    root = client.post("/api/projects/one/note-folders", headers=ORIGIN, json={"name": "Root"}).json()
    child = client.post(
        "/api/projects/one/note-folders", headers=ORIGIN, json={"name": "Child", "parent_id": root["id"]}
    ).json()
    assert client.post("/api/projects/one/note-folders", headers=ORIGIN, json={"name": "Root"}).status_code == 409
    assert (
        client.post(
            "/api/projects/two/note-folders", headers=ORIGIN, json={"name": "Cross", "parent_id": root["id"]}
        ).status_code
        == 404
    )
    assert (
        client.patch(f"/api/note-folders/{root['id']}", headers=ORIGIN, json={"parent_id": child["id"]}).status_code
        == 409
    )
    assert (
        client.post("/api/projects/one/notes", headers=ORIGIN, json={"title": "Same", "markdown": ""}).status_code
        == 201
    )
    assert (
        client.post("/api/projects/one/notes", headers=ORIGIN, json={"title": "Same", "markdown": ""}).status_code
        == 409
    )


def test_note_acl_inspection_and_cross_project_wiki_links(client: TestClient) -> None:
    login(client)
    create_user(client, "alice")
    client.cookies.clear()
    change_temporary_password(client, "alice", "temporary-alice-123", "alice-new-password-123")
    for key in ("private", "other"):
        assert (
            client.post(
                "/api/projects", headers=ORIGIN, json={"key": key, "name": key.title(), "notes_enabled": True}
            ).status_code
            == 201
        )
    folder = client.post("/api/projects/private/note-folders", headers=ORIGIN, json={"name": "Docs"}).json()
    secret = client.post(
        "/api/projects/other/notes", headers=ORIGIN, json={"title": "Secret title", "markdown": "secret"}
    ).json()
    note = client.post(
        "/api/projects/private/notes",
        headers=ORIGIN,
        json={"title": "Public", "markdown": f"[[N-{secret['id']}]]", "folder_id": folder["id"]},
    ).json()
    assert client.get(f"/api/notes/{note['id']}").json()["references"] == []
    client.cookies.clear()
    login(client)
    assert client.get(f"/api/notes/{note['id']}").status_code == 404
    assert client.get(f"/api/notes/{note['id']}?inspection=true").status_code == 200
    assert client.get("/api/projects/private/note-folders?inspection=true").status_code == 200
    assert client.get(f"/api/notes/{note['id']}/revisions?inspection=true").status_code == 200


def test_mcp_note_tools_are_home_project_scoped_and_versioned(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    login(client)
    assert (
        client.post(
            "/api/projects", headers=ORIGIN, json={"key": "home", "name": "Home", "notes_enabled": True}
        ).status_code
        == 201
    )
    secret = client.post("/api/mcp-keys", headers=ORIGIN, json={"name": "notes-key"}).json()["secret"]
    monkeypatch.setattr(
        mcp_server,
        "get_http_headers",
        lambda **_: {"authorization": f"Bearer {secret}", "x-home-project": "home"},
    )
    folder = mcp_server.create_note_folder("Docs")
    note = mcp_server.create_note("MCP", "body", folder["id"])
    assert mcp_server.get_note(note["id"])["creator"] == "Admin"
    assert mcp_server.move_note(note["id"], None, 1)["version"] == 2
    with pytest.raises(ValueError):
        mcp_server.archive_note(note["id"], 1)
    assert len(mcp_server.list_notes(limit=1)) == 1
    assert client.post("/api/projects", headers=ORIGIN, json={"key": "disabled", "name": "Disabled"}).status_code == 201
    monkeypatch.setattr(
        mcp_server,
        "get_http_headers",
        lambda **_: {"authorization": f"Bearer {secret}", "x-home-project": "disabled"},
    )
    with pytest.raises(ValueError, match="Notes are disabled"):
        mcp_server.list_notes()
