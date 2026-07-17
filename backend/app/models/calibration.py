"""Immutable Phase 2 calibration profile persistence model."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    Index,
    Integer,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.calibration_contracts import MARKER_BORDER_BITS, ArucoDictionary
from backend.app.database import Base


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""

    return datetime.now(UTC)


aruco_dictionary_type = Enum(
    ArucoDictionary,
    values_callable=lambda enum: [member.value for member in enum],
    native_enum=False,
    create_constraint=False,
    validate_strings=True,
    length=16,
)


class CalibrationProfile(Base):
    """An immutable marker configuration with separately managed activation state."""

    __tablename__ = "calibration_profiles"
    __table_args__ = (
        CheckConstraint(
            "dictionary IN ('DICT_4X4_50', 'DICT_5X5_50', 'DICT_6X6_50')",
            name="ck_calibration_profiles_dictionary",
        ),
        CheckConstraint("marker_id BETWEEN 0 AND 49", name="ck_calibration_profiles_marker_id"),
        CheckConstraint("marker_size_mm BETWEEN 10 AND 300", name="ck_calibration_profiles_size"),
        CheckConstraint("border_bits = 1", name="ck_calibration_profiles_border_bits"),
        CheckConstraint(
            "minimum_marker_side_px BETWEEN 24 AND 4096",
            name="ck_calibration_profiles_minimum_side",
        ),
        CheckConstraint(
            "maximum_perspective_ratio BETWEEN 1.0 AND 10.0",
            name="ck_calibration_profiles_perspective_ratio",
        ),
        CheckConstraint(
            "maximum_homography_condition_number BETWEEN 10.0 AND 1000000000000.0",
            name="ck_calibration_profiles_homography_condition",
        ),
        CheckConstraint(
            "maximum_marker_edge_residual_px BETWEEN 0.1 AND 20.0",
            name="ck_calibration_profiles_edge_residual",
        ),
        CheckConstraint(
            "rectified_pixels_per_mm BETWEEN 1.0 AND 6.0",
            name="ck_calibration_profiles_rectified_scale",
        ),
        Index("ix_calibration_profiles_created_at", "created_at"),
        Index(
            "uq_calibration_profiles_single_active",
            "is_active",
            unique=True,
            sqlite_where=text("is_active = 1"),
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    dictionary: Mapped[ArucoDictionary] = mapped_column(
        aruco_dictionary_type,
        nullable=False,
    )
    marker_id: Mapped[int] = mapped_column(Integer, nullable=False)
    marker_size_mm: Mapped[float] = mapped_column(Float, nullable=False)
    border_bits: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=MARKER_BORDER_BITS,
        server_default=text("1"),
    )
    minimum_marker_side_px: Mapped[int] = mapped_column(Integer, nullable=False)
    maximum_perspective_ratio: Mapped[float] = mapped_column(Float, nullable=False)
    maximum_homography_condition_number: Mapped[float] = mapped_column(Float, nullable=False)
    maximum_marker_edge_residual_px: Mapped[float] = mapped_column(Float, nullable=False)
    rectified_pixels_per_mm: Mapped[float] = mapped_column(Float, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("0"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

