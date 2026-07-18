"""Phase 3 immutable measurement attempts and private evidence metadata."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.database import Base
from backend.app.measurement_contracts import (
    MeasurementStatus,
    MeasurementView,
    PreviewKind,
)


def utc_now() -> datetime:
    return datetime.now(UTC)


measurement_status_type = Enum(
    MeasurementStatus,
    values_callable=lambda enum: [member.value for member in enum],
    native_enum=False,
    create_constraint=False,
    validate_strings=True,
    length=16,
)
measurement_view_type = Enum(
    MeasurementView,
    values_callable=lambda enum: [member.value for member in enum],
    native_enum=False,
    create_constraint=False,
    validate_strings=True,
    length=16,
)
preview_kind_type = Enum(
    PreviewKind,
    values_callable=lambda enum: [member.value for member in enum],
    native_enum=False,
    create_constraint=False,
    validate_strings=True,
    length=16,
)


class MeasurementAttempt(Base):
    """One immutable terminal result or actively leased processing attempt."""

    __tablename__ = "measurement_attempts"
    __table_args__ = (
        CheckConstraint(
            "status IN ('processing', 'succeeded', 'failed')",
            name="ck_measurement_attempts_status",
        ),
        CheckConstraint(
            "length_mm IS NULL OR length_mm > 0",
            name="ck_measurement_attempts_length_positive",
        ),
        CheckConstraint(
            "width_mm IS NULL OR width_mm > 0",
            name="ck_measurement_attempts_width_positive",
        ),
        CheckConstraint(
            "height_mm IS NULL OR height_mm > 0",
            name="ck_measurement_attempts_height_positive",
        ),
        CheckConstraint(
            "(status = 'processing' AND completed_at IS NULL AND failure_json IS NULL "
            "AND length_mm IS NULL AND width_mm IS NULL AND height_mm IS NULL) OR "
            "(status = 'succeeded' AND completed_at IS NOT NULL AND failure_json IS NULL "
            "AND length_mm IS NOT NULL AND width_mm IS NOT NULL AND height_mm IS NOT NULL "
            "AND source_fingerprint IS NOT NULL AND per_view_evidence_json IS NOT NULL "
            "AND reconciliation_evidence_json IS NOT NULL AND quality_evidence_json IS NOT NULL "
            "AND uncertainty_evidence_json IS NOT NULL AND warnings_json IS NOT NULL) OR "
            "(status = 'failed' AND completed_at IS NOT NULL AND failure_json IS NOT NULL "
            "AND length_mm IS NULL AND width_mm IS NULL AND height_mm IS NULL)",
            name="ck_measurement_attempts_state_shape",
        ),
        UniqueConstraint(
            "scan_id", "request_id", name="uq_measurement_attempts_scan_request"
        ),
        Index("ix_measurement_attempts_scan_created", "scan_id", "created_at"),
        Index("ix_measurement_attempts_profile", "calibration_profile_id"),
        Index("ix_measurement_attempts_status", "status"),
        Index(
            "uq_measurement_attempts_processing_scan",
            "scan_id",
            unique=True,
            sqlite_where=text("status = 'processing'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    scan_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scans.id", ondelete="CASCADE"), nullable=False
    )
    request_id: Mapped[str] = mapped_column(String(36), nullable=False)
    request_signature: Mapped[str] = mapped_column(Text, nullable=False)
    reprocess_of_measurement_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("measurement_attempts.id", ondelete="RESTRICT")
    )
    calibration_profile_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("calibration_profiles.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[MeasurementStatus] = mapped_column(
        measurement_status_type,
        nullable=False,
        default=MeasurementStatus.PROCESSING,
        server_default=text("'processing'"),
    )
    processing_version: Mapped[str] = mapped_column(String(64), nullable=False)
    algorithm_version: Mapped[str] = mapped_column(String(64), nullable=False)
    profile_snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    capture_setup_snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    measurement_policy_snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    source_fingerprint: Mapped[str | None] = mapped_column(String(64))
    length_mm: Mapped[float | None] = mapped_column(Float)
    width_mm: Mapped[float | None] = mapped_column(Float)
    height_mm: Mapped[float | None] = mapped_column(Float)
    per_view_evidence_json: Mapped[str | None] = mapped_column(Text)
    reconciliation_evidence_json: Mapped[str | None] = mapped_column(Text)
    quality_evidence_json: Mapped[str | None] = mapped_column(Text)
    uncertainty_evidence_json: Mapped[str | None] = mapped_column(Text)
    warnings_json: Mapped[str | None] = mapped_column(Text)
    failure_json: Mapped[str | None] = mapped_column(Text)
    lease_token: Mapped[str] = mapped_column(String(36), nullable=False)
    lease_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sources: Mapped[list[MeasurementSource]] = relationship(
        back_populates="attempt",
        cascade="all, delete-orphan",
        order_by=lambda: MeasurementSource.view,
    )
    previews: Mapped[list[MeasurementPreview]] = relationship(
        back_populates="attempt",
        cascade="all, delete-orphan",
        order_by=lambda: MeasurementPreview.view,
    )


class MeasurementSource(Base):
    """Private snapshot of one required source image for an attempt."""

    __tablename__ = "measurement_sources"
    __table_args__ = (
        CheckConstraint("view IN ('top', 'front', 'side')", name="ck_measurement_sources_view"),
        CheckConstraint("size_bytes > 0", name="ck_measurement_sources_size_positive"),
        CheckConstraint("width_px > 0", name="ck_measurement_sources_width_positive"),
        CheckConstraint("height_px > 0", name="ck_measurement_sources_height_positive"),
        UniqueConstraint(
            "measurement_attempt_id", "view", name="uq_measurement_sources_attempt_view"
        ),
        Index("ix_measurement_sources_attempt", "measurement_attempt_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    measurement_attempt_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("measurement_attempts.id", ondelete="CASCADE"), nullable=False
    )
    view: Mapped[MeasurementView] = mapped_column(measurement_view_type, nullable=False)
    scan_image_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scan_images.id", ondelete="RESTRICT"), nullable=False
    )
    storage_key_snapshot: Mapped[str] = mapped_column(String(512), nullable=False)
    original_sha256: Mapped[str | None] = mapped_column(String(64))
    oriented_pixel_sha256: Mapped[str | None] = mapped_column(String(64))
    media_type: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    width_px: Mapped[int] = mapped_column(Integer, nullable=False)
    height_px: Mapped[int] = mapped_column(Integer, nullable=False)
    attempt: Mapped[MeasurementAttempt] = relationship(back_populates="sources")


class MeasurementPreview(Base):
    """Private metadata for one server-generated PNG preview."""

    __tablename__ = "measurement_previews"
    __table_args__ = (
        CheckConstraint("view IN ('top', 'front', 'side')", name="ck_measurement_previews_view"),
        CheckConstraint("kind = 'annotated'", name="ck_measurement_previews_kind"),
        CheckConstraint("media_type = 'image/png'", name="ck_measurement_previews_media_type"),
        CheckConstraint("size_bytes > 0", name="ck_measurement_previews_size_positive"),
        CheckConstraint("width_px > 0", name="ck_measurement_previews_width_positive"),
        CheckConstraint("height_px > 0", name="ck_measurement_previews_height_positive"),
        UniqueConstraint(
            "measurement_attempt_id",
            "view",
            "kind",
            name="uq_measurement_previews_attempt_view_kind",
        ),
        Index("ix_measurement_previews_attempt", "measurement_attempt_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    measurement_attempt_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("measurement_attempts.id", ondelete="CASCADE"), nullable=False
    )
    view: Mapped[MeasurementView] = mapped_column(measurement_view_type, nullable=False)
    kind: Mapped[PreviewKind] = mapped_column(preview_kind_type, nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    media_type: Mapped[str] = mapped_column(String(32), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    width_px: Mapped[int] = mapped_column(Integer, nullable=False)
    height_px: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    attempt: Mapped[MeasurementAttempt] = relationship(back_populates="previews")
