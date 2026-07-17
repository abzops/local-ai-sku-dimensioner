"""Establish the Phase 0 database baseline.

Revision ID: 0001_phase0
Revises:
Create Date: 2026-07-17
"""

from collections.abc import Sequence

revision: str = "0001_phase0"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create only Alembic's version table in Phase 0."""


def downgrade() -> None:
    """No domain schema exists to remove in Phase 0."""

