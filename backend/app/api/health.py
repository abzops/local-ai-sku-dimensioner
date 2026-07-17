"""Application health API."""

from typing import cast

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from backend.app import __version__
from backend.app.config import Settings
from backend.app.database import Database
from backend.app.schemas.errors import ErrorResponse
from backend.app.schemas.health import ComponentHealth, HealthResponse

router = APIRouter()


def database_unavailable_response() -> JSONResponse:
    """Return the stable, sanitized database readiness failure contract."""
    error = ErrorResponse(
        code="DATABASE_UNAVAILABLE",
        message="The local database is unavailable or has not been initialized.",
        recoverable=True,
        suggested_action="Run scripts/setup_windows.ps1, then restart the application.",
    )
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content=error.model_dump(),
    )


@router.get(
    "/health",
    response_model=HealthResponse,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse}},
)
def health(request: Request) -> HealthResponse | JSONResponse:
    """Report application and migration readiness without leaking local paths."""
    settings = cast(Settings, request.app.state.settings)
    database = cast(Database | None, request.app.state.database)

    if database is None:
        return database_unavailable_response()

    try:
        revision = database.check_readiness()
    except (OSError, RuntimeError, SQLAlchemyError):
        return database_unavailable_response()

    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=__version__,
        database=ComponentHealth(status="ok", revision=revision),
    )
