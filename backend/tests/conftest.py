"""Shared backend test fixtures."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from backend.app.config import REPOSITORY_ROOT, Settings, get_settings

ISOLATED_SETTINGS_ENVIRONMENT = {
    "DATA_ROOT",
    "DATABASE_URL",
    "FRONTEND_DIST_DIR",
    "LOG_LEVEL",
    "MAX_ADDITIONAL_IMAGES",
    "MAX_IMAGE_PIXELS",
    "MAX_UPLOAD_FILES_PER_REQUEST",
    "MAX_UPLOAD_MB",
    "MIN_IMAGE_LONG_EDGE",
    "MIN_IMAGE_SHORT_EDGE",
}


def is_settings_environment_name(name: str) -> bool:
    return name.startswith(("APP_", "CAPTURE_SETUP_", "MEASUREMENT_")) or (
        name in ISOLATED_SETTINGS_ENVIRONMENT
    )


INHERITED_SETTINGS_ENVIRONMENT = {
    name: value
    for name, value in os.environ.items()
    if is_settings_environment_name(name)
}
for inherited_name in INHERITED_SETTINGS_ENVIRONMENT:
    os.environ.pop(inherited_name, None)


@pytest.fixture(autouse=True)
def isolate_settings_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Prevent caller configuration from changing backend test behavior."""
    inherited_names = tuple(os.environ)
    for name in inherited_names:
        if is_settings_environment_name(name):
            monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Restore the parent environment after the isolated test session."""
    del session, exitstatus
    for name in tuple(os.environ):
        if is_settings_environment_name(name):
            os.environ.pop(name, None)
    os.environ.update(INHERITED_SETTINGS_ENVIRONMENT)
    get_settings.cache_clear()


def upgrade_database(database_url: str) -> None:
    config = Config(str(REPOSITORY_ROOT / "alembic.ini"))
    config.set_main_option(
        "script_location",
        str(REPOSITORY_ROOT / "backend" / "migrations"),
    )
    config.attributes["database_url"] = database_url
    command.upgrade(config, "head")


@pytest.fixture
def database_url(tmp_path: Path) -> str:
    path = tmp_path / "database" / "test.db"
    return f"sqlite+pysqlite:///{path.as_posix()}"


@pytest.fixture
def migrated_database_url(database_url: str) -> str:
    upgrade_database(database_url)
    return database_url


@pytest.fixture
def app_settings(tmp_path: Path, migrated_database_url: str) -> Iterator[Settings]:
    settings = Settings(
        _env_file=None,
        app_env="test",
        data_root=tmp_path,
        database_url=migrated_database_url,
        frontend_dist_dir=tmp_path / "missing-dist",
        max_upload_mb=1,
        min_image_long_edge=12,
        min_image_short_edge=8,
        max_image_pixels=1_000_000,
        max_additional_images=5,
        max_upload_files_per_request=8,
    )
    yield settings
