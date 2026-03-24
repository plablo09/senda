"""add_session_expires_at_index

Revision ID: 0003
Revises: 0002
Create Date: 2026-03-23

"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_sesiones_refresh_expires_at", "sesiones_refresh", ["expires_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_sesiones_refresh_expires_at", table_name="sesiones_refresh")
