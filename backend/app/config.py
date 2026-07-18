"""Typed application configuration."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def default_data_root() -> Path:
    """Return a non-synchronised per-user runtime directory when possible."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "LocalAISkuDimensioner"
    return Path.home() / ".local" / "share" / "local-ai-sku-dimensioner"


class Settings(BaseSettings):
    """Configuration loaded from environment variables and the root .env file."""

    model_config = SettingsConfigDict(
        env_file=REPOSITORY_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )

    app_name: str = "Local AI SKU Dimensioner"
    app_env: Literal["development", "production", "test"] = "development"
    app_host: Literal["127.0.0.1", "localhost"] = "127.0.0.1"
    app_port: int = 8000
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    data_root: Path = Field(default_factory=default_data_root)
    database_url: str | None = None
    frontend_dist_dir: Path = REPOSITORY_ROOT / "frontend" / "dist"
    max_upload_mb: int = 25
    min_image_long_edge: int = 1280
    min_image_short_edge: int = 720
    max_image_pixels: int = 60_000_000
    max_additional_images: int = 5
    max_upload_files_per_request: int = 8
    capture_setup_id: str = "unconfigured"
    capture_setup_version: str = "unconfigured"
    capture_setup_qualified: bool = False
    capture_setup_type: Literal["orthogonal_rig"] = "orthogonal_rig"
    capture_setup_min_object_mm: float = 75.0
    capture_setup_max_object_mm: float = 400.0
    capture_setup_marker_size_uncertainty_mm: float = 0.5
    capture_setup_plane_uncertainty_mm: float = 1.0
    capture_setup_orthogonality_uncertainty_deg: float = 0.5
    capture_setup_standoff_uncertainty_mm: float = 2.0
    capture_setup_max_off_plane_mm: float = 0.0
    measurement_acceptable_disagreement_mm: float = 5.0
    measurement_acceptable_disagreement_percent: float = 3.0
    measurement_warning_disagreement_mm: float = 10.0
    measurement_warning_disagreement_percent: float = 6.0
    measurement_usable_quality: float = 0.70
    measurement_weak_quality: float = 0.55
    measurement_stronger_source_quality_lead: float = 0.15
    measurement_weaker_source_uncertainty_ratio: float = 2.0
    measurement_max_rectified_edge_px: int = 4096
    measurement_max_rectified_pixels: int = 16_000_000
    measurement_max_physical_extent_mm: float = 1500.0
    measurement_max_components: int = 1024
    measurement_max_candidates: int = 64
    measurement_processing_deadline_seconds: float = 30.0
    measurement_processing_lease_seconds: int = 120

    @field_validator("app_port")
    @classmethod
    def validate_port(cls, value: int) -> int:
        if not 1 <= value <= 65535:
            raise ValueError("APP_PORT must be between 1 and 65535")
        return value

    @field_validator("max_upload_mb")
    @classmethod
    def validate_max_upload_mb(cls, value: int) -> int:
        if not 1 <= value <= 100:
            raise ValueError("MAX_UPLOAD_MB must be between 1 and 100")
        return value

    @field_validator("min_image_long_edge", "min_image_short_edge")
    @classmethod
    def validate_minimum_image_edge(cls, value: int) -> int:
        if not 1 <= value <= 20_000:
            raise ValueError("Minimum image edges must be between 1 and 20000 pixels")
        return value

    @field_validator("max_image_pixels")
    @classmethod
    def validate_max_image_pixels(cls, value: int) -> int:
        if not 1 <= value <= 200_000_000:
            raise ValueError("MAX_IMAGE_PIXELS must be between 1 and 200000000")
        return value

    @field_validator("max_additional_images", "max_upload_files_per_request")
    @classmethod
    def validate_upload_count(cls, value: int) -> int:
        if not 1 <= value <= 50:
            raise ValueError("Upload file counts must be between 1 and 50")
        return value

    @model_validator(mode="after")
    def validate_upload_limit_relationships(self) -> Settings:
        if self.min_image_short_edge > self.min_image_long_edge:
            raise ValueError(
                "MIN_IMAGE_SHORT_EDGE cannot exceed MIN_IMAGE_LONG_EDGE"
            )
        if self.max_upload_files_per_request < 3:
            raise ValueError("MAX_UPLOAD_FILES_PER_REQUEST must allow three required views")
        if self.max_additional_images > self.max_upload_files_per_request:
            raise ValueError(
                "MAX_ADDITIONAL_IMAGES cannot exceed MAX_UPLOAD_FILES_PER_REQUEST"
            )
        return self

    @field_validator("capture_setup_id")
    @classmethod
    def validate_capture_setup_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Capture setup ID cannot be empty")
        if len(normalized) > 100:
            raise ValueError("Capture setup ID cannot exceed 100 characters")
        if any(character in normalized for character in ("/", "\\", "\x00")):
            raise ValueError("Capture setup ID cannot contain path separators")
        return normalized

    @field_validator("capture_setup_version")
    @classmethod
    def validate_capture_setup_version(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Capture setup version cannot be empty")
        if len(normalized) > 50:
            raise ValueError("Capture setup version cannot exceed 50 characters")
        if any(character in normalized for character in ("/", "\\", "\x00")):
            raise ValueError("Capture setup version cannot contain path separators")
        return normalized

    @field_validator(
        "capture_setup_min_object_mm",
        "capture_setup_max_object_mm",
        "measurement_acceptable_disagreement_mm",
        "measurement_acceptable_disagreement_percent",
        "measurement_warning_disagreement_mm",
        "measurement_warning_disagreement_percent",
        "measurement_max_physical_extent_mm",
        "measurement_processing_deadline_seconds",
        "measurement_weaker_source_uncertainty_ratio",
    )
    @classmethod
    def validate_positive_measurement_value(cls, value: float) -> float:
        if not 0.0 < value <= 1_000_000.0:
            raise ValueError("Measurement configuration values must be finite and positive")
        return value

    @field_validator(
        "capture_setup_marker_size_uncertainty_mm",
        "capture_setup_plane_uncertainty_mm",
        "capture_setup_orthogonality_uncertainty_deg",
        "capture_setup_standoff_uncertainty_mm",
        "capture_setup_max_off_plane_mm",
    )
    @classmethod
    def validate_non_negative_uncertainty(cls, value: float) -> float:
        if not 0.0 <= value <= 10_000.0:
            raise ValueError("Capture uncertainty values must be finite and non-negative")
        return value

    @field_validator(
        "measurement_usable_quality",
        "measurement_weak_quality",
        "measurement_stronger_source_quality_lead",
    )
    @classmethod
    def validate_quality_threshold(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("Measurement quality thresholds must be between zero and one")
        return value

    @field_validator(
        "measurement_max_rectified_edge_px",
        "measurement_max_rectified_pixels",
        "measurement_max_components",
        "measurement_max_candidates",
        "measurement_processing_lease_seconds",
    )
    @classmethod
    def validate_positive_measurement_integer(cls, value: int) -> int:
        if not 1 <= value <= 200_000_000:
            raise ValueError("Measurement resource limits must be positive")
        return value

    @model_validator(mode="after")
    def validate_phase3_relationships(self) -> Settings:
        if self.capture_setup_min_object_mm >= self.capture_setup_max_object_mm:
            raise ValueError(
                "CAPTURE_SETUP_MIN_OBJECT_MM must be below CAPTURE_SETUP_MAX_OBJECT_MM"
            )
        if self.capture_setup_qualified and (
            self.capture_setup_id.casefold() == "unconfigured"
            or self.capture_setup_version.casefold() == "unconfigured"
        ):
            raise ValueError(
                "A qualified capture setup requires an explicit ID and version"
            )
        if (
            self.measurement_acceptable_disagreement_mm
            > self.measurement_warning_disagreement_mm
            or self.measurement_acceptable_disagreement_percent
            > self.measurement_warning_disagreement_percent
        ):
            raise ValueError(
                "Acceptable disagreement thresholds cannot exceed warning thresholds"
            )
        if self.measurement_weak_quality > self.measurement_usable_quality:
            raise ValueError(
                "MEASUREMENT_WEAK_QUALITY cannot exceed MEASUREMENT_USABLE_QUALITY"
            )
        if self.measurement_max_candidates > self.measurement_max_components:
            raise ValueError(
                "MEASUREMENT_MAX_CANDIDATES cannot exceed MEASUREMENT_MAX_COMPONENTS"
            )
        if (
            self.measurement_max_rectified_edge_px
            * self.measurement_max_rectified_edge_px
            < self.measurement_max_rectified_pixels
        ):
            raise ValueError(
                "MEASUREMENT_MAX_RECTIFIED_PIXELS cannot exceed the square edge ceiling"
            )
        if (
            self.measurement_processing_lease_seconds
            <= self.measurement_processing_deadline_seconds
        ):
            raise ValueError(
                "MEASUREMENT_PROCESSING_LEASE_SECONDS must exceed "
                "MEASUREMENT_PROCESSING_DEADLINE_SECONDS"
            )
        return self

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not value.startswith(("sqlite:///", "sqlite+pysqlite:///")):
            raise ValueError("Phase 0 supports local SQLite database URLs only")
        return value

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        database_path = (self.data_root / "database" / "app.db").resolve()
        return f"sqlite+pysqlite:///{database_path.as_posix()}"

    @property
    def max_upload_bytes(self) -> int:
        """Return the per-file upload limit in bytes."""
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance."""
    return Settings()
