"""Configuration behavior tests."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.app.config import Settings


def test_default_data_root_uses_local_app_data(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    settings = Settings(_env_file=None)

    assert settings.data_root == tmp_path / "LocalAISkuDimensioner"
    assert settings.resolved_database_url.endswith(
        "/LocalAISkuDimensioner/database/app.db"
    )


def test_environment_override_is_loaded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_PORT", "8123")

    settings = Settings(_env_file=None)

    assert settings.app_port == 8123


def test_non_loopback_host_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_host="0.0.0.0")


def test_non_sqlite_database_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, database_url="postgresql://localhost/app")

