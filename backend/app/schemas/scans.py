"""Public Phase 1 scan request and response schemas."""

from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from backend.app.contracts import ImageView, ScanStatus

SkuValue = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class CreateScanRequest(BaseModel):
    """Metadata accepted when creating an empty draft scan."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    sku: SkuValue
    barcode: str | None = Field(default=None, max_length=128)
    product_name: str | None = Field(default=None, max_length=200)

    @field_validator("barcode", "product_name", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: Any) -> Any:
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None
        return value


class ScanImageResponse(BaseModel):
    """Safe image metadata with all storage details excluded."""

    model_config = ConfigDict(frozen=True, from_attributes=True)

    id: str
    view_type: ImageView
    media_type: Literal["image/jpeg", "image/png", "image/webp"]
    size_bytes: int
    width_px: int
    height_px: int
    created_at: datetime

    @field_validator("created_at", mode="after")
    @classmethod
    def normalize_created_at_timezone(cls, value: datetime) -> datetime:
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class ScanMetadataResponse(BaseModel):
    """Fields shared by scan summaries and details."""

    model_config = ConfigDict(frozen=True)

    id: str
    sku: str
    barcode: str | None
    product_name: str | None
    status: ScanStatus
    missing_required_views: list[ImageView]
    created_at: datetime
    updated_at: datetime

    @field_validator("created_at", "updated_at", mode="after")
    @classmethod
    def normalize_timestamp_timezone(cls, value: datetime) -> datetime:
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class ScanSummary(ScanMetadataResponse):
    image_count: int


class ScanDetail(ScanMetadataResponse):
    images: list[ScanImageResponse]


class ScanListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[ScanSummary]
    total: int
    offset: int
    limit: int


class UploadBatchResponse(BaseModel):
    """Updated scan plus only the image metadata inserted by this request."""

    model_config = ConfigDict(frozen=True)

    scan: ScanDetail
    uploaded_images: list[ScanImageResponse]
