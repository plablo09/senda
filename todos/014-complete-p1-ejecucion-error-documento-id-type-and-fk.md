---
status: complete
priority: p1
issue_id: "014"
tags: [code-review, alembic, migrations, schema, types, foreign-key]
dependencies: []
---

# Fix `ejecucion_errores.documento_id`: String(36) → UUID + add FK constraint

## Problem Statement

`ejecucion_errores.documento_id` is typed `String(36)` in both the ORM model and the initial Alembic migration. `documentos.id` is a native PostgreSQL `uuid` column. These are incompatible types at the database level — PostgreSQL will not allow a foreign key constraint between them, and any `JOIN` or comparison across these columns requires an explicit `CAST`. There is also no FK constraint at all, meaning orphaned error records can accumulate silently if documents are deleted.

This is a P1 because the Phase 4 plan explicitly calls for changing `documento_id` to a UUID FK (migration `0004`). If this type mismatch is left as-is, that future migration will require a destructive `ALTER COLUMN … USING documento_id::uuid` cast — a more complex and risky migration than necessary. The cost to fix it now is zero (greenfield, no data).

## Findings

- `api/models/ejecucion_error.py:19` — `documento_id: Mapped[str | None] = mapped_column(String(36), nullable=True)` — should be `Mapped[uuid.UUID | None]` with `sa.UUID()`
- `alembic/versions/0001_initial_schema.py:40` — `sa.Column("documento_id", sa.String(length=36), nullable=True)` — should be `sa.UUID()`
- Neither the model nor the migration define a FK constraint to `documentos.id`
- Flagged as P1 by 3 independent review agents (kieran-python-reviewer, architecture-strategist, data-migration-expert)

## Proposed Solutions

### Option A: Fix type + add FK in 0001 migration (Recommended)

**In `api/models/ejecucion_error.py`:**
```python
import uuid
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
import sqlalchemy as sa

documento_id: Mapped[uuid.UUID | None] = mapped_column(
    sa.UUID(), ForeignKey("documentos.id", ondelete="SET NULL"), nullable=True
)
```

**In `alembic/versions/0001_initial_schema.py`:**
```python
op.create_table(
    "ejecucion_errores",
    sa.Column("id", sa.UUID(), nullable=False),
    sa.Column("documento_id", sa.UUID(), nullable=True),  # changed from String(36)
    ...
    sa.PrimaryKeyConstraint("id"),
    sa.ForeignKeyConstraint(["documento_id"], ["documentos.id"], ondelete="SET NULL"),
)
```

- **Pros:** Correct at every layer (Python type, SQLAlchemy type, DB type, referential integrity)
- **Cons:** None — this is a greenfield schema with no existing data

### Option B: Leave as String(36) and add a comment documenting the deliberate loose coupling

- **Pros:** Consistent with current session_id String(36) pattern
- **Cons:** Incompatible with Phase 4 plan; will require a destructive ALTER COLUMN later; no referential integrity

**Recommended:** Option A.

## Related: `session_id` String(36)

`session_id` in `ejecucion_errores` is also `String(36)` — but this one is a WebSocket session identifier, not a database UUID FK. If sessions are always UUID-shaped, consider changing to `sa.UUID()` for consistency. If they may be non-UUID strings, add a comment documenting this. Low priority compared to `documento_id`, but worth deciding in the same commit.

## Acceptance Criteria

- [ ] `ejecucion_errores.documento_id` is `sa.UUID()` in both model and migration
- [ ] FK constraint `REFERENCES documentos(id) ON DELETE SET NULL` exists in migration `0001`
- [ ] `alembic check` passes (model and migration agree)
- [ ] All 59 existing unit tests pass

## Work Log

- 2026-03-22: Flagged as P1 by kieran-python-reviewer, architecture-strategist (P1-1, P1-2) and P2 by data-migration-expert in Phase 1 Alembic review. Consensus: fix now while greenfield.
