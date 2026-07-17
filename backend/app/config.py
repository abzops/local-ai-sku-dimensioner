"""Typed application configuration."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
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

    @field_validator("app_port")
    @classmethod
    def validate_port(cls, value: int) -> int:
        if not 1 <= value <= 65535:
            raise ValueError("APP_PORT must be between 1 and 65535")
        return value

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


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance."""
    return Settings()
