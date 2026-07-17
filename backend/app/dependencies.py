"""FastAPI dependencies shared by Phase 1 database-backed routes."""

from collections.abc import Iterator
from typing import Annotated, cast

from fastapi import Depends, Request, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.config import Settings
from backend.app.database import Database
from backend.app.errors import ApplicationError


def get_ready_database(request: Request) -> Database:
    """Return the ready application database or a sanitized public error."""
    database = cast(Database | None, request.app.state.database)
    if database is not None:
        try:
            database.check_readiness()
            return database
        except (OSError, RuntimeError, SQLAlchemyError):
            pass
    raise ApplicationError(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        code="DATABASE_UNAVAILABLE",
        message="The local database is unavailable or has not been initialized.",
        recoverable=True,
        suggested_action="Run scripts/setup_windows.ps1, then restart the application.",
    )


def get_session(
    database: Annotated[Database, Depends(get_ready_database)],
) -> Iterator[Session]:
    """Yield one short-lived SQLAlchemy session for an API request."""
    with database.session_factory() as session:
        yield session


SessionDependency = Annotated[Session, Depends(get_session)]


def get_active_settings(request: Request) -> Settings:
    """Return the settings instance used to construct the active application."""
    return cast(Settings, request.app.state.settings)


SettingsDependency = Annotated[Settings, Depends(get_active_settings)]
