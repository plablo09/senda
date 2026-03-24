---
status: pending
priority: p2
issue_id: "032"
tags: [code-review, database, migration]
dependencies: []
---

# Add DB Trigger for usuarios.updated_at

## Problem Statement

`usuarios.updated_at` has only a Python-side `onupdate=lambda: datetime.now(UTC)` ORM hook. This fires only when SQLAlchemy flushes a tracked ORM object. Any UPDATE that bypasses the ORM (admin scripts, bulk updates via `db.execute(update(...))`, direct SQL) will leave `updated_at` frozen at the original `created_at` value — silently stale.

## Findings

- `api/models/usuario.py:35`: `onupdate=lambda: datetime.now(UTC)` — Python-level hook only
- `alembic/versions/0002_add_usuarios_and_refresh_sessions.py:38–43`: No `BEFORE UPDATE` trigger created
- Bulk ORM operations like `await db.execute(update(Usuario).where(...).values(...))` bypass per-row hooks
- `docs/solutions/runtime-errors/async-python-fastapi-sqlalchemy-impl-pitfalls.md` confirms: `onupdate` fires only through the ORM flush path
- Migration expert: P1-B — stale `updated_at` silently breaks any audit trail or cache invalidation that reads this column

## Proposed Solutions

### Option 1: Add BEFORE UPDATE trigger in migration (Recommended)

**Approach:** Create a reusable `set_updated_at()` trigger function and attach it to `usuarios`.

```sql
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER usuarios_set_updated_at
BEFORE UPDATE ON usuarios
FOR EACH ROW EXECUTE FUNCTION set_updated_at();
```

Add to migration 0003 (alongside session cleanup index from todo-024).

**Pros:**
- `updated_at` is correct regardless of how rows are modified
- Reusable function can be applied to any future table
- One-time setup

**Cons:**
- Trigger adds minor overhead per UPDATE row (negligible for user management)

**Effort:** 30 minutes

**Risk:** Low

## Recommended Action

Add to migration 0003. The function `set_updated_at()` can be reused when `documentos` and `datasets` tables get `updated_at` triggers in a future migration.

## Technical Details

**Affected files:**
- New migration 0003 — add trigger function + trigger

**Downgrade:**
```sql
DROP TRIGGER IF EXISTS usuarios_set_updated_at ON usuarios;
DROP FUNCTION IF EXISTS set_updated_at;
```

## Acceptance Criteria

- [ ] Migration 0003 includes trigger function and trigger creation
- [ ] `UPDATE usuarios SET email='...' WHERE id='...'` via raw SQL updates `updated_at`
- [ ] Bulk ORM update (`db.execute(update(Usuario)...)`) updates `updated_at`
- [ ] Downgrade drops trigger and function cleanly

## Work Log

### 2026-03-23 - Identified in code review

**By:** Claude Code (ce-review)
