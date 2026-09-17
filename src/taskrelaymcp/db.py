from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, event, select
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


def init_db() -> None:
    from taskrelaymcp import models  # noqa: F401

    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    _bootstrap()


def _bootstrap() -> None:
    from taskrelaymcp.auth import hash_password
    from taskrelaymcp.config import bootstrap_admin
    from taskrelaymcp.models import User

    configured = bootstrap_admin()
    with session_scope() as session:
        user = session.scalar(select(User).where(User.username == configured.username))
        if not user:
            user = User(
                username=configured.username,
                display_name=configured.display_name,
                password_hash=hash_password(configured.password),
                active=True,
                is_admin=True,
                must_change_password=False,
            )
            session.add(user)
            session.flush()
        elif not user.is_admin:
            raise RuntimeError("Bootstrap username exists but is not an administrator")


@contextmanager
def session_scope() -> Iterator[Session]:
    with SessionLocal() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
