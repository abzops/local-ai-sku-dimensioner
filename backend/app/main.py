"""FastAPI application entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from logging import getLogger

from fastapi import FastAPI
from sqlalchemy.exc import SQLAlchemyError

from backend.app import __version__
from backend.app.api.router import api_router
from backend.app.config import Settings, get_settings
from backend.app.database import Database
from backend.app.frontend import mount_frontend
from backend.app.logging_config import configure_logging

logger = getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create an independently configurable application instance."""
    active_settings = settings or get_settings()
    configure_logging(active_settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        database: Database | None = None
        app.state.database = None
        app.state.database_initialization_error = None
        try:
            database = Database(active_settings.resolved_database_url)
            app.state.database = database
        except (OSError, RuntimeError, SQLAlchemyError, ValueError):
            app.state.database_initialization_error = "DATABASE_INITIALIZATION_FAILED"
            logger.error("Database initialization failed; application started in degraded mode.")
        try:
            yield
        finally:
            if database is not None:
                database.dispose()

    application = FastAPI(
        title=active_settings.app_name,
        version=__version__,
        lifespan=lifespan,
    )
    application.state.settings = active_settings
    application.include_router(api_router, prefix="/api")
    application.state.frontend_mounted = mount_frontend(
        application,
        active_settings.frontend_dist_dir,
    )
    return application


app = create_app()
