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
