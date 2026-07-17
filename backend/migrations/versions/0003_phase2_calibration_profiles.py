"""Add immutable Phase 2 calibration profiles.

Revision ID: 0003_phase2_calibration_profiles
Revises: 0002_phase1_scans
Create Date: 2026-07-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_phase2_calibration_profiles"
down_revision: str | None = "0002_phase1_scans"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "calibration_profiles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("dictionary", sa.String(length=16), nullable=False),
        sa.Column("marker_id", sa.Integer(), nullable=False),
        sa.Column("marker_size_mm", sa.Float(), nullable=False),
        sa.Column("border_bits", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("minimum_marker_side_px", sa.Integer(), nullable=False),
        sa.Column("maximum_perspective_ratio", sa.Float(), nullable=False),
        sa.Column("maximum_homography_condition_number", sa.Float(), nullable=False),
        sa.Column("maximum_marker_edge_residual_px", sa.Float(), nullable=False),
        sa.Column("rectified_pixels_per_mm", sa.Float(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "dictionary IN ('DICT_4X4_50', 'DICT_5X5_50', 'DICT_6X6_50')",
            name="ck_calibration_profiles_dictionary",
        ),
        sa.CheckConstraint(
            "marker_id BETWEEN 0 AND 49",
            name="ck_calibration_profiles_marker_id",
        ),
        sa.CheckConstraint(
            "marker_size_mm BETWEEN 10 AND 300",
            name="ck_calibration_profiles_size",
        ),
        sa.CheckConstraint("border_bits = 1", name="ck_calibration_profiles_border_bits"),
        sa.CheckConstraint(
            "minimum_marker_side_px BETWEEN 24 AND 4096",
            name="ck_calibration_profiles_minimum_side",
        ),
        sa.CheckConstraint(
            "maximum_perspective_ratio BETWEEN 1.0 AND 10.0",
            name="ck_calibration_profiles_perspective_ratio",
        ),
        sa.CheckConstraint(
            "maximum_homography_condition_number BETWEEN 10.0 AND 1000000000000.0",
            name="ck_calibration_profiles_homography_condition",
        ),
        sa.CheckConstraint(
            "maximum_marker_edge_residual_px BETWEEN 0.1 AND 20.0",
            name="ck_calibration_profiles_edge_residual",
        ),
        sa.CheckConstraint(
            "rectified_pixels_per_mm BETWEEN 1.0 AND 6.0",
            name="ck_calibration_profiles_rectified_scale",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(
        "ix_calibration_profiles_created_at",
        "calibration_profiles",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "uq_calibration_profiles_single_active",
        "calibration_profiles",
        ["is_active"],
        unique=True,
        sqlite_where=sa.text("is_active = 1"),
    )


def downgrade() -> None:
    op.drop_index("uq_calibration_profiles_single_active", table_name="calibration_profiles")
    op.drop_index("ix_calibration_profiles_created_at", table_name="calibration_profiles")
    op.drop_table("calibration_profiles")

