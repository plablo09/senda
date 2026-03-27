---
status: pending
priority: p2
issue_id: "043"
tags: [code-review, database, migration, trigger]
dependencies: ["042"]
---

# Add DB-Level `updated_at` Trigger to `documentos` Table

## Problem Statement

Migration 0005 adds a PostgreSQL `BEFORE UPDATE` trigger to `usuarios` to keep `updated_at` current at the database level. The `documentos` table has the same `updated_at` column with the same `onupdate=lambda: datetime.now(UTC)` ORM hook, but no corresponding DB trigger. This inconsistency means:

1. Bulk `UPDATE` statements or direct SQL writes on `documentos` silently leave `updated_at` stale
2. Tests that read `doc.updated_at` without a `session.refresh()` may see the ORM-managed value rather than the DB value (clock skew risk)
3. When Phase 3 adds more tables, the pattern is ambiguous — which tables get DB-level protection?

## Findings

- `api/models/documento.py:40` — `updated_at: Mapped[datetime] = mapped_column(..., onupdate=lambda: datetime.now(UTC))` — ORM only
- `api/models/usuario.py:38` — same column definition
- `alembic/versions/0005:31-45` — trigger and function created for `usuarios` only
- `alembic/versions/0005:32` — `CREATE OR REPLACE FUNCTION set_updated_at()` — the shared function already exists; `documentos` just needs its own trigger
- Confirmed by: schema-drift-detector (Finding 3), data-migration-expert (Issue 4)

## Proposed Solutions

### Option 1: Add migration 0006 with `documentos` trigger (Recommended)

Create a new migration that adds `CREATE TRIGGER documentos_set_updated_at BEFORE UPDATE ON documentos FOR EACH ROW EXECUTE FUNCTION set_updated_at()`. No new function needed — reuse the one from 0005.

**Pros:** Consistent with `usuarios`; protects against direct SQL writes; future tables just need the trigger
**Cons:** One more migration file; depends on 0005 being applied first
**Effort:** 15 minutes
**Risk:** Low

### Option 2: Add the trigger to migration 0005

Extend the existing 0005 migration to also add the trigger on `documentos`.

**Pros:** Fewer migration files
**Cons:** Modifies an existing migration — only safe before this branch is merged to main; after merge, a new migration is required
**Effort:** 10 minutes
**Risk:** Low if done before merge, high if done after

## Recommended Action

Option 2 before merge (add to migration 0005); Option 1 after merge. Since this branch has not merged yet, adding the `documentos` trigger to migration 0005 is the cleanest approach.

## Technical Details

**Affected files:**
- `alembic/versions/0005_auth_db_constraints_and_updated_at_trigger.py` — add trigger for `documentos`
- Downgrade must drop `documentos_set_updated_at` trigger before dropping the function

## Acceptance Criteria

- [ ] `documentos` table has a `BEFORE UPDATE` trigger calling `set_updated_at()`
- [ ] `alembic upgrade head` creates the trigger on `documentos`
- [ ] `alembic downgrade 0004` removes both triggers cleanly
- [ ] Direct SQL `UPDATE documentos SET titulo = 'x' WHERE id = ?` advances `updated_at`

## Work Log

### 2026-03-26 - Identified during ce-review

**By:** Claude Code (ce-review)
