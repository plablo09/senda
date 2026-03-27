"""auth_db_constraints_and_updated_at_trigger

Revision ID: 0005
Revises: 0004
Create Date: 2026-03-26

"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # CHECK constraint: only 'teacher' and 'student' are valid roles
    op.create_check_constraint(
        "ck_usuarios_rol",
        "usuarios",
        "rol IN ('teacher', 'student')",
    )

    # Reusable trigger function: keeps updated_at current on every UPDATE,
    # regardless of whether the change goes through the ORM or raw SQL.
    op.execute("""
        CREATE OR REPLACE FUNCTION set_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE OR REPLACE TRIGGER usuarios_set_updated_at
        BEFORE UPDATE ON usuarios
        FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS usuarios_set_updated_at ON usuarios;")
    # NOTE: set_updated_at() is a shared function intended for reuse across tables.
    # Do not drop it here — a future migration may have attached it to other tables.
    # Drop it only in a dedicated teardown migration once no triggers reference it.
    op.drop_constraint("ck_usuarios_rol", "usuarios", type_="check")
