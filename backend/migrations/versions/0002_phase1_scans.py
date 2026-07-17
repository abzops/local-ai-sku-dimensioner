"""Add Phase 1 scan and image records.

Revision ID: 0002_phase1_scans
Revises: 0001_phase0
Create Date: 2026-07-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_phase1_scans"
down_revision: str | None = "0001_phase0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scans",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("sku", sa.String(length=100), nullable=False),
        sa.Column("barcode", sa.String(length=128), nullable=True),
        sa.Column("product_name", sa.String(length=200), nullable=True),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default=sa.text("'draft'"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'images_uploaded', 'ready_for_processing')",
            name="ck_scans_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_scans_created_at", "scans", ["created_at"], unique=False)
    op.create_index("ix_scans_sku", "scans", ["sku"], unique=False)
    op.create_index("ix_scans_barcode", "scans", ["barcode"], unique=False)

    op.create_table(
        "scan_images",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("scan_id", sa.String(length=36), nullable=False),
        sa.Column("view_type", sa.String(length=16), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("media_type", sa.String(length=64), nullable=False),
        sa.Column("file_extension", sa.String(length=8), nullable=False),
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
            "view_type IN ('top', 'front', 'side', 'additional')",
            name="ck_scan_images_view_type",
        ),
        sa.CheckConstraint("size_bytes > 0", name="ck_scan_images_size_bytes_positive"),
        sa.CheckConstraint("width_px > 0", name="ck_scan_images_width_px_positive"),
        sa.CheckConstraint("height_px > 0", name="ck_scan_images_height_px_positive"),
        sa.ForeignKeyConstraint(["scan_id"], ["scans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key", name="uq_scan_images_storage_key"),
    )
    op.create_index("ix_scan_images_scan_id", "scan_images", ["scan_id"], unique=False)
    op.create_index(
        "uq_scan_images_required_view",
        "scan_images",
        ["scan_id", "view_type"],
        unique=True,
        sqlite_where=sa.text("view_type IN ('top', 'front', 'side')"),
    )


def downgrade() -> None:
    op.drop_index("uq_scan_images_required_view", table_name="scan_images")
    op.drop_index("ix_scan_images_scan_id", table_name="scan_images")
    op.drop_table("scan_images")
    op.drop_index("ix_scans_barcode", table_name="scans")
    op.drop_index("ix_scans_sku", table_name="scans")
    op.drop_index("ix_scans_created_at", table_name="scans")
    op.drop_table("scans")
