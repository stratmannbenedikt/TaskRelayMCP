from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, event
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

    Base.metadata.create_all(engine)


@contextmanager
def session_scope() -> Iterator[Session]:
    with SessionLocal() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
