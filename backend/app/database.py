"""SQLite engine lifecycle and readiness checks."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic.util.exc import CommandError
from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.app.config import REPOSITORY_ROOT


class Base(DeclarativeBase):
    """Base class reserved for Phase 1 database models."""


def ensure_sqlite_parent(database_url: str) -> None:
    """Create the parent folder for a file-backed SQLite database."""
    url = make_url(database_url)
    if url.get_backend_name() != "sqlite":
        raise ValueError("Only SQLite is supported")
    if url.database and url.database != ":memory:":
        Path(url.database).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)


def expected_alembic_head() -> str:
    """Return the single migration head shipped with this application."""
    config = Config()
    config.set_main_option(
        "script_location",
        str(REPOSITORY_ROOT / "backend" / "migrations"),
    )
    try:
        heads = ScriptDirectory.from_config(config).get_heads()
    except CommandError as error:
        raise RuntimeError("Application migration metadata is unavailable") from error
    if len(heads) != 1:
        raise RuntimeError("Application migration metadata must have exactly one head")
    return heads[0]


class Database:
    """Own the SQLAlchemy engine used by one application instance."""

    def __init__(self, database_url: str) -> None:
        ensure_sqlite_parent(database_url)
        self.engine = create_engine(
            database_url,
            connect_args={"check_same_thread": False},
            pool_pre_ping=True,
        )
        self._configure_sqlite(self.engine)
        self.session_factory = sessionmaker(
            bind=self.engine,
            class_=Session,
            expire_on_commit=False,
        )

    @staticmethod
    def _configure_sqlite(engine: Engine) -> None:
        @event.listens_for(engine, "connect")
        def set_sqlite_pragmas(
            dbapi_connection: Any,
            _connection_record: Any,
        ) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

    def check_connection(self) -> None:
        """Raise if SQLite cannot execute a basic query."""
        with self.engine.connect() as connection:
            connection.execute(text("SELECT 1"))

    def current_revision(self) -> str:
        """Return the current revision only when it matches the application head."""
        with self.engine.connect() as connection:
            revision = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one_or_none()
        if not revision:
            raise RuntimeError("Database migration state is unavailable")
        current_revision = str(revision)
        if current_revision != expected_alembic_head():
            raise RuntimeError("Database migration state does not match application head")
        return current_revision

    def check_readiness(self) -> str:
        """Validate connectivity and return the verified migration head."""
        self.check_connection()
        return self.current_revision()

    def dispose(self) -> None:
        """Close pooled database connections."""
        self.engine.dispose()
