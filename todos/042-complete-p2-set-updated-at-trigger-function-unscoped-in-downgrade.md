---
status: pending
priority: p2
issue_id: "042"
tags: [code-review, migration, database, trigger]
dependencies: []
---

# Scope `set_updated_at` Function Removal in Migration 0005 Downgrade

## Problem Statement

Migration 0005 creates `set_updated_at()` as a generic, reusable PL/pgSQL function intended for multiple tables. The `downgrade()` at line 50 calls `DROP FUNCTION IF EXISTS set_updated_at` unconditionally. If any future migration adds this trigger to a second table (e.g., `documentos`) and someone downgrades past 0005 while those later migrations are still applied, the shared function is dropped while the other table's trigger still references it. Any subsequent `UPDATE` on that table raises `ERROR: function set_updated_at() does not exist`.

## Findings

- `alembic/versions/0005_auth_db_constraints_and_updated_at_trigger.py:50` — `DROP FUNCTION IF EXISTS set_updated_at` in downgrade
- `alembic/versions/0005_auth_db_constraints_and_updated_at_trigger.py:32` — `CREATE OR REPLACE FUNCTION set_updated_at()` — intended as reusable
- `api/models/documento.py:40` — `documentos.updated_at` has `onupdate=lambda: datetime.now(UTC)` but no DB trigger — a future migration will likely add one using the same function
- Confirmed by: data-migration-expert (Issue 2), kieran-python-reviewer (low), schema-drift-detector (Finding 3)

## Proposed Solutions

### Option 1: Guard the function drop with a `pg_depend` check (Recommended)

In the downgrade, check whether any trigger still references `set_updated_at` before dropping it:

```sql
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_proc p
    JOIN pg_depend d ON d.objid = p.oid
    WHERE p.proname = 'set_updated_at' AND d.deptype = 'n'
  ) THEN
    DROP FUNCTION IF EXISTS set_updated_at;
  END IF;
END $$;
```

**Pros:** Safe for any future use of the shared function
**Cons:** More complex SQL; `pg_depend` semantics can be subtle
**Effort:** 30 minutes
**Risk:** Low

### Option 2: Never drop the function in 0005's downgrade

Remove the `DROP FUNCTION IF EXISTS set_updated_at` line from the downgrade entirely. The function is harmless if present without any triggers using it. A dedicated tear-down migration can remove it when no tables use it.

**Pros:** Safest option; simplest change; function is benign if orphaned
**Cons:** Function lingers in the DB after downgrade (cosmetic)
**Effort:** 1 minute
**Risk:** None

### Option 3: Rename to table-scoped function `usuarios_set_updated_at`

Make the function table-specific so downgrade can safely drop it without cross-table risk.

**Pros:** Eliminates the sharing concern entirely
**Cons:** Every future table needing this trigger must define its own function; drift between functions possible
**Effort:** 15 minutes (update migration + trigger)
**Risk:** Low

## Recommended Action

Option 2 before merge — remove the `DROP FUNCTION IF EXISTS set_updated_at` line from the 0005 downgrade. Add a comment explaining the function is shared and should be dropped only when no triggers reference it. A future migration (when all triggers are eventually removed) can handle the teardown.

## Technical Details

**Affected files:**
- `alembic/versions/0005_auth_db_constraints_and_updated_at_trigger.py:50`

## Acceptance Criteria

- [ ] `DROP FUNCTION IF EXISTS set_updated_at` removed from 0005 downgrade (or guarded)
- [ ] `alembic downgrade 0004` succeeds without dropping a still-referenced function
- [ ] `alembic upgrade head && alembic downgrade 0004 && alembic upgrade head` cycle completes cleanly

## Work Log

### 2026-03-26 - Identified during ce-review

**By:** Claude Code (ce-review)
