"""add_estado_render_check_constraint

Revision ID: 0004
Revises: 0003
Create Date: 2026-03-26

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_documento_estado_render",
        "documentos",
        "estado_render IN ('pendiente', 'procesando', 'listo', 'fallido')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_documento_estado_render", "documentos", type_="check"
    )
