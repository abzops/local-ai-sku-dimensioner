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


def test_upload_defaults_are_bounded() -> None:
    settings = Settings(_env_file=None)

    assert settings.max_upload_bytes == 25 * 1024 * 1024
    assert settings.min_image_long_edge == 1280
    assert settings.min_image_short_edge == 720
    assert settings.max_additional_images == 5
    assert settings.max_upload_files_per_request == 8


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("max_upload_mb", 0),
        ("max_image_pixels", 0),
        ("max_additional_images", 0),
        ("max_upload_files_per_request", 2),
    ],
)
def test_invalid_upload_limits_are_rejected(field: str, value: int) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{field: value})


def test_short_image_edge_cannot_exceed_long_edge() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            min_image_short_edge=1281,
            min_image_long_edge=1280,
        )


def test_measurement_lease_must_exceed_processing_deadline() -> None:
    with pytest.raises(ValidationError, match="LEASE_SECONDS must exceed"):
        Settings(
            _env_file=None,
            measurement_processing_deadline_seconds=120.0,
            measurement_processing_lease_seconds=120,
        )

    settings = Settings(
        _env_file=None,
        measurement_processing_deadline_seconds=119.5,
        measurement_processing_lease_seconds=120,
    )

    assert settings.measurement_processing_lease_seconds == 120


def test_capture_setup_version_accepts_exactly_fifty_characters() -> None:
    version = "v" * 50

    settings = Settings(_env_file=None, capture_setup_version=version)

    assert settings.capture_setup_version == version


def test_capture_setup_version_rejects_fifty_one_characters() -> None:
    with pytest.raises(ValidationError, match="cannot exceed 50 characters"):
        Settings(_env_file=None, capture_setup_version="v" * 51)


@pytest.mark.parametrize("version", ["", "   "])
def test_capture_setup_version_rejects_empty_or_whitespace(version: str) -> None:
    with pytest.raises(ValidationError, match="cannot be empty"):
        Settings(_env_file=None, capture_setup_version=version)


def test_capture_setup_version_preserves_valid_content_after_trimming() -> None:
    settings = Settings(_env_file=None, capture_setup_version="  rig-v1  ")

    assert settings.capture_setup_version == "rig-v1"
