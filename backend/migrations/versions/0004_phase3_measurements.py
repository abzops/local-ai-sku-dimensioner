"""Add immutable Phase 3 measurement attempts and evidence metadata.

Revision ID: 0004_phase3_measurements
Revises: 0003_phase2_calibration_profiles
Create Date: 2026-07-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_phase3_measurements"
down_revision: str | None = "0003_phase2_calibration_profiles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "measurement_attempts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("scan_id", sa.String(length=36), nullable=False),
        sa.Column("request_id", sa.String(length=36), nullable=False),
        sa.Column("request_signature", sa.Text(), nullable=False),
        sa.Column("reprocess_of_measurement_id", sa.String(length=36), nullable=True),
        sa.Column("calibration_profile_id", sa.String(length=36), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default=sa.text("'processing'"),
            nullable=False,
        ),
        sa.Column("processing_version", sa.String(length=64), nullable=False),
        sa.Column("algorithm_version", sa.String(length=64), nullable=False),
        sa.Column("profile_snapshot_json", sa.Text(), nullable=False),
        sa.Column("capture_setup_snapshot_json", sa.Text(), nullable=False),
        sa.Column("measurement_policy_snapshot_json", sa.Text(), nullable=False),
        sa.Column("source_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("length_mm", sa.Float(), nullable=True),
        sa.Column("width_mm", sa.Float(), nullable=True),
        sa.Column("height_mm", sa.Float(), nullable=True),
        sa.Column("per_view_evidence_json", sa.Text(), nullable=True),
        sa.Column("reconciliation_evidence_json", sa.Text(), nullable=True),
        sa.Column("quality_evidence_json", sa.Text(), nullable=True),
        sa.Column("uncertainty_evidence_json", sa.Text(), nullable=True),
        sa.Column("warnings_json", sa.Text(), nullable=True),
        sa.Column("failure_json", sa.Text(), nullable=True),
        sa.Column("lease_token", sa.String(length=36), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('processing', 'succeeded', 'failed')",
            name="ck_measurement_attempts_status",
        ),
        sa.CheckConstraint(
            "length_mm IS NULL OR length_mm > 0",
            name="ck_measurement_attempts_length_positive",
        ),
        sa.CheckConstraint(
            "width_mm IS NULL OR width_mm > 0",
            name="ck_measurement_attempts_width_positive",
        ),
        sa.CheckConstraint(
            "height_mm IS NULL OR height_mm > 0",
            name="ck_measurement_attempts_height_positive",
        ),
        sa.CheckConstraint(
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
        sa.ForeignKeyConstraint(["scan_id"], ["scans.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["reprocess_of_measurement_id"], ["measurement_attempts.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["calibration_profile_id"], ["calibration_profiles.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "scan_id", "request_id", name="uq_measurement_attempts_scan_request"
        ),
    )
    op.create_index(
        "ix_measurement_attempts_scan_created",
        "measurement_attempts",
        ["scan_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_measurement_attempts_profile",
        "measurement_attempts",
        ["calibration_profile_id"],
        unique=False,
    )
    op.create_index(
        "ix_measurement_attempts_status",
        "measurement_attempts",
        ["status"],
        unique=False,
    )
    op.create_index(
        "uq_measurement_attempts_processing_scan",
        "measurement_attempts",
        ["scan_id"],
        unique=True,
        sqlite_where=sa.text("status = 'processing'"),
    )

    op.create_table(
        "measurement_sources",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("measurement_attempt_id", sa.String(length=36), nullable=False),
        sa.Column("view", sa.String(length=16), nullable=False),
        sa.Column("scan_image_id", sa.String(length=36), nullable=False),
        sa.Column("storage_key_snapshot", sa.String(length=512), nullable=False),
        sa.Column("original_sha256", sa.String(length=64), nullable=True),
        sa.Column("oriented_pixel_sha256", sa.String(length=64), nullable=True),
        sa.Column("media_type", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("width_px", sa.Integer(), nullable=False),
        sa.Column("height_px", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "view IN ('top', 'front', 'side')", name="ck_measurement_sources_view"
        ),
        sa.CheckConstraint("size_bytes > 0", name="ck_measurement_sources_size_positive"),
        sa.CheckConstraint("width_px > 0", name="ck_measurement_sources_width_positive"),
        sa.CheckConstraint("height_px > 0", name="ck_measurement_sources_height_positive"),
        sa.ForeignKeyConstraint(
            ["measurement_attempt_id"], ["measurement_attempts.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["scan_image_id"], ["scan_images.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "measurement_attempt_id", "view", name="uq_measurement_sources_attempt_view"
        ),
    )
    op.create_index(
        "ix_measurement_sources_attempt",
        "measurement_sources",
        ["measurement_attempt_id"],
        unique=False,
    )

    op.create_table(
        "measurement_previews",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("measurement_attempt_id", sa.String(length=36), nullable=False),
        sa.Column("view", sa.String(length=16), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("media_type", sa.String(length=32), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("width_px", sa.Integer(), nullable=False),
        sa.Column("height_px", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "view IN ('top', 'front', 'side')", name="ck_measurement_previews_view"
        ),
        sa.CheckConstraint("kind = 'annotated'", name="ck_measurement_previews_kind"),
        sa.CheckConstraint("media_type = 'image/png'", name="ck_measurement_previews_media_type"),
        sa.CheckConstraint("size_bytes > 0", name="ck_measurement_previews_size_positive"),
        sa.CheckConstraint("width_px > 0", name="ck_measurement_previews_width_positive"),
        sa.CheckConstraint("height_px > 0", name="ck_measurement_previews_height_positive"),
        sa.ForeignKeyConstraint(
            ["measurement_attempt_id"], ["measurement_attempts.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "measurement_attempt_id",
            "view",
            "kind",
            name="uq_measurement_previews_attempt_view_kind",
        ),
    )
    op.create_index(
        "ix_measurement_previews_attempt",
        "measurement_previews",
        ["measurement_attempt_id"],
        unique=False,
    )

    _create_immutability_triggers()


def downgrade() -> None:
    for trigger in (
        "trg_measurement_previews_terminal_insert",
        "trg_measurement_previews_terminal_update",
        "trg_measurement_previews_terminal_delete",
        "trg_measurement_sources_terminal_insert",
        "trg_measurement_sources_terminal_update",
        "trg_measurement_sources_terminal_delete",
        "trg_measurement_attempts_terminal_update",
        "trg_measurement_attempts_terminal_delete",
    ):
        op.execute(sa.text(f"DROP TRIGGER IF EXISTS {trigger}"))
    op.drop_index("ix_measurement_previews_attempt", table_name="measurement_previews")
    op.drop_table("measurement_previews")
    op.drop_index("ix_measurement_sources_attempt", table_name="measurement_sources")
    op.drop_table("measurement_sources")
    op.drop_index("uq_measurement_attempts_processing_scan", table_name="measurement_attempts")
    op.drop_index("ix_measurement_attempts_status", table_name="measurement_attempts")
    op.drop_index("ix_measurement_attempts_profile", table_name="measurement_attempts")
    op.drop_index("ix_measurement_attempts_scan_created", table_name="measurement_attempts")
    op.drop_table("measurement_attempts")


def _create_immutability_triggers() -> None:
    op.execute(
        sa.text(
            """
            CREATE TRIGGER trg_measurement_attempts_terminal_update
            BEFORE UPDATE ON measurement_attempts
            WHEN OLD.status IN ('succeeded', 'failed')
            BEGIN
                SELECT RAISE(ABORT, 'terminal measurement attempt is immutable');
            END
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TRIGGER trg_measurement_attempts_terminal_delete
            BEFORE DELETE ON measurement_attempts
            WHEN OLD.status IN ('succeeded', 'failed')
            BEGIN
                SELECT RAISE(ABORT, 'terminal measurement attempt is immutable');
            END
            """
        )
    )
    for table in ("measurement_sources", "measurement_previews"):
        for operation in ("INSERT", "UPDATE", "DELETE"):
            row_alias = "NEW" if operation in {"INSERT", "UPDATE"} else "OLD"
            op.execute(
                sa.text(
                    f"""
                    CREATE TRIGGER trg_{table}_terminal_{operation.lower()}
                    BEFORE {operation} ON {table}
                    WHEN EXISTS (
                        SELECT 1 FROM measurement_attempts
                        WHERE id = {row_alias}.measurement_attempt_id
                          AND status IN ('succeeded', 'failed')
                    )
                    BEGIN
                        SELECT RAISE(ABORT, 'terminal measurement evidence is immutable');
                    END
                    """
                )
            )
