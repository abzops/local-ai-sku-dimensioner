"""Health endpoint response models."""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class ComponentHealth(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: Literal["ok"]
    revision: str


class HealthResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: Literal["ok"]
    service: str
    version: str
    database: ComponentHealth

