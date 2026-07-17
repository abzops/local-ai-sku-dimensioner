"""Phase 1 scan and image persistence models."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.contracts import ImageView, ScanStatus
from backend.app.database import Base


def utc_now() -> datetime:
    """Return a timezone-aware timestamp for new and updated records."""
    return datetime.now(UTC)


scan_status_type = Enum(
    ScanStatus,
    values_callable=lambda enum: [member.value for member in enum],
    native_enum=False,
    create_constraint=False,
    validate_strings=True,
    length=32,
)
image_view_type = Enum(
    ImageView,
    values_callable=lambda enum: [member.value for member in enum],
    native_enum=False,
    create_constraint=False,
    validate_strings=True,
    length=16,
)


class Scan(Base):
    """A locally persisted SKU scan and its upload readiness state."""

    __tablename__ = "scans"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'images_uploaded', 'ready_for_processing')",
            name="ck_scans_status",
        ),
        Index("ix_scans_created_at", "created_at"),
        Index("ix_scans_sku", "sku"),
        Index("ix_scans_barcode", "barcode"),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    sku: Mapped[str] = mapped_column(String(100), nullable=False)
    barcode: Mapped[str | None] = mapped_column(String(128))
    product_name: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[ScanStatus] = mapped_column(
        scan_status_type,
        nullable=False,
        default=ScanStatus.DRAFT,
        server_default=text("'draft'"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    images: Mapped[list[ScanImage]] = relationship(
        back_populates="scan",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by=lambda: (ScanImage.created_at, ScanImage.id),
    )


class ScanImage(Base):
    """Metadata for a validated image stored outside SQLite."""

    __tablename__ = "scan_images"
    __table_args__ = (
        CheckConstraint(
            "view_type IN ('top', 'front', 'side', 'additional')",
            name="ck_scan_images_view_type",
        ),
        CheckConstraint("size_bytes > 0", name="ck_scan_images_size_bytes_positive"),
        CheckConstraint("width_px > 0", name="ck_scan_images_width_px_positive"),
        CheckConstraint("height_px > 0", name="ck_scan_images_height_px_positive"),
        UniqueConstraint("storage_key", name="uq_scan_images_storage_key"),
        Index("ix_scan_images_scan_id", "scan_id"),
        Index(
            "uq_scan_images_required_view",
            "scan_id",
            "view_type",
            unique=True,
            sqlite_where=text("view_type IN ('top', 'front', 'side')"),
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    scan_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("scans.id", ondelete="CASCADE"),
        nullable=False,
    )
    view_type: Mapped[ImageView] = mapped_column(image_view_type, nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    media_type: Mapped[str] = mapped_column(String(64), nullable=False)
    file_extension: Mapped[str] = mapped_column(String(8), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    width_px: Mapped[int] = mapped_column(Integer, nullable=False)
    height_px: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    scan: Mapped[Scan] = relationship(back_populates="images")
