"""initial_schema

Revision ID: 0001
Revises:
Create Date: 2026-03-22

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "documentos",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("titulo", sa.String(length=500), nullable=False),
        sa.Column("ast", sa.JSON(), nullable=True),
        sa.Column("qmd_source", sa.Text(), nullable=True),
        sa.Column("estado_render", sa.String(length=50), nullable=False, server_default="pendiente"),
        sa.Column("url_artefacto", sa.String(length=2048), nullable=True),
        sa.Column("error_render", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "ejecucion_errores",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("documento_id", sa.UUID(), nullable=True),
        sa.Column("ejercicio_id", sa.String(length=255), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("error_tipo", sa.String(length=50), nullable=False),
        sa.Column("error_output", sa.Text(), nullable=True),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["documento_id"], ["documentos.id"], ondelete="SET NULL"),
    )

    op.create_table(
        "datasets",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("mimetype", sa.String(length=100), nullable=False),
        sa.Column("es_publico", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS datasets")
    op.execute("DROP TABLE IF EXISTS ejecucion_errores")
    op.drop_table("documentos")
