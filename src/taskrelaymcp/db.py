from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, create_engine, event, inspect
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from taskrelaymcp.config import database_url


class Base(DeclarativeBase):
    pass


def _engine(url: str | None = None) -> Engine:
    engine = create_engine(url or database_url(), connect_args={"check_same_thread": False})

    if engine.url.get_backend_name() == "sqlite":

        @event.listens_for(engine, "connect")
        def configure_sqlite(dbapi_connection: object, _: object) -> None:
            cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

    return engine


engine = _engine()
SessionLocal = sessionmaker(engine, expire_on_commit=False)

V01_REVISION = "0001_v01_baseline"
V01_TABLES = {
    "comments": {
        "id": ("INTEGER", False),
        "task_id": ("INTEGER", False),
        "author": ("TEXT", False),
        "body": ("TEXT", False),
        "created_at": ("NUMERIC", False),
    },
    "notifications": {
        "id": ("INTEGER", False),
        "project_id": ("INTEGER", False),
        "task_id": ("INTEGER", False),
        "type": ("TEXT", False),
        "message": ("TEXT", False),
        "created_at": ("NUMERIC", False),
        "read_at": ("NUMERIC", True),
    },
    "projects": {
        "id": ("INTEGER", False),
        "key": ("TEXT", False),
        "name": ("TEXT", False),
        "description": ("TEXT", False),
        "color": ("TEXT", True),
        "archived": ("NUMERIC", False),
        "created_at": ("NUMERIC", False),
    },
    "tags": {"id": ("INTEGER", False), "name": ("TEXT", False)},
    "task_events": {
        "id": ("INTEGER", False),
        "task_id": ("INTEGER", False),
        "actor": ("TEXT", False),
        "event_type": ("TEXT", False),
        "payload_json": ("TEXT", False),
        "created_at": ("NUMERIC", False),
    },
    "task_tags": {"task_id": ("INTEGER", False), "tag_id": ("INTEGER", False)},
    "tasks": {
        "id": ("INTEGER", False),
        "title": ("TEXT", False),
        "description": ("TEXT", False),
        "status": ("TEXT", False),
        "priority": ("TEXT", False),
        "target_project_id": ("INTEGER", False),
        "origin_project_id": ("INTEGER", False),
        "created_by": ("TEXT", False),
        "assigned_agent": ("TEXT", True),
        "created_at": ("NUMERIC", False),
        "updated_at": ("NUMERIC", False),
        "completed_at": ("NUMERIC", True),
    },
}
V01_FOREIGN_KEYS = {
    "comments": {(("task_id",), "tasks", ("id",), "CASCADE")},
    "notifications": {(("project_id",), "projects", ("id",), None), (("task_id",), "tasks", ("id",), "CASCADE")},
    "projects": set(),
    "tags": set(),
    "task_events": {(("task_id",), "tasks", ("id",), "CASCADE")},
    "task_tags": {(("task_id",), "tasks", ("id",), "CASCADE"), (("tag_id",), "tags", ("id",), "CASCADE")},
    "tasks": {(("target_project_id",), "projects", ("id",), None), (("origin_project_id",), "projects", ("id",), None)},
}
V01_INDEXES = {
    "comments": {"ix_comments_task_id": (("task_id",), False)},
    "notifications": {
        "ix_notifications_project_id": (("project_id",), False),
        "ix_notifications_task_id": (("task_id",), False),
    },
    "projects": {"ix_projects_key": (("key",), True)},
    "tags": {"ix_tags_name": (("name",), True)},
    "task_events": {"ix_task_events_task_id": (("task_id",), False)},
    "task_tags": {},
    "tasks": {},
}


def _affinity(type_name: str) -> str:
    name = type_name.upper()
    if "INT" in name:
        return "INTEGER"
    if any(token in name for token in ("CHAR", "CLOB", "TEXT")):
        return "TEXT"
    if "BLOB" in name or not name:
        return "BLOB"
    if any(token in name for token in ("REAL", "FLOA", "DOUB")):
        return "REAL"
    return "NUMERIC"


def _is_v01_schema(connection: Connection) -> bool:
    inspector = inspect(connection)
    if set(inspector.get_table_names()) != set(V01_TABLES):
        return False
    for table, columns in V01_TABLES.items():
        actual_columns = {
            column["name"]: (_affinity(str(column["type"])), column["nullable"])
            for column in inspector.get_columns(table)
        }
        foreign_keys = {
            (
                tuple(item["constrained_columns"]),
                item["referred_table"],
                tuple(item["referred_columns"]),
                item["options"].get("ondelete"),
            )
            for item in inspector.get_foreign_keys(table)
        }
        indexes = {
            item["name"]: (tuple(item["column_names"]), bool(item["unique"])) for item in inspector.get_indexes(table)
        }
        if actual_columns != columns or foreign_keys != V01_FOREIGN_KEYS[table] or indexes != V01_INDEXES[table]:
            return False
        if inspector.get_pk_constraint(table)["constrained_columns"] != ["id"] and table not in {"task_tags"}:
            return False
        if table == "task_tags" and inspector.get_pk_constraint(table)["constrained_columns"] != ["task_id", "tag_id"]:
            return False
        if inspector.get_unique_constraints(table):
            return False
    return True


def init_db() -> None:
    from taskrelaymcp import models  # noqa: F401

    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    with engine.begin() as connection:
        tables = set(inspect(connection).get_table_names())
        if "alembic_version" not in tables and tables:
            if not _is_v01_schema(connection):
                raise RuntimeError("Refusing to adopt a database that does not exactly match the frozen v0.1 schema")
            config.attributes["connection"] = connection
            command.stamp(config, V01_REVISION)
        config.attributes["connection"] = connection
        command.upgrade(config, "head")


@contextmanager
def session_scope() -> Iterator[Session]:
    with SessionLocal() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
