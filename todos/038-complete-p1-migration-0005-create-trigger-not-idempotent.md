---
status: pending
priority: p1
issue_id: "038"
tags: [code-review, migration, database, trigger]
dependencies: []
---

# Make `CREATE TRIGGER` in Migration 0005 Idempotent

## Problem Statement

Migration `0005_auth_db_constraints_and_updated_at_trigger.py` creates the `usuarios_set_updated_at` trigger with a plain `CREATE TRIGGER` statement. There is no `IF NOT EXISTS` guard and no `CREATE OR REPLACE TRIGGER` form. If the migration is run against a database where the trigger already exists (CI snapshot restore, manual replay, Alembic version table manipulation), it will fail with `ERROR: trigger "usuarios_set_updated_at" for relation "usuarios" already exists` and leave Alembic in a partially-applied state.

By contrast, the function creation on the line above correctly uses `CREATE OR REPLACE FUNCTION` — the trigger is the only non-idempotent object in the migration.

## Findings

- `alembic/versions/0005_auth_db_constraints_and_updated_at_trigger.py:41-45` — `CREATE TRIGGER usuarios_set_updated_at ...` — no `OR REPLACE`
- `alembic/versions/0005_auth_db_constraints_and_updated_at_trigger.py:32` — `CREATE OR REPLACE FUNCTION set_updated_at()` — correctly idempotent
- PostgreSQL 14+ supports `CREATE OR REPLACE TRIGGER` — the project uses PostgreSQL 16 (confirmed in docker-compose.yml)
- Confirmed by: data-migration-expert (Issue 3)

## Proposed Solutions

### Option 1: Use `CREATE OR REPLACE TRIGGER` (Recommended for PG 14+)

Replace `CREATE TRIGGER` with `CREATE OR REPLACE TRIGGER` on line 41.

**Pros:** Single-line fix; idempotent; semantically correct
**Cons:** Requires PostgreSQL 14+ (project uses PG 16 — no issue)
**Effort:** 1 minute
**Risk:** None

### Option 2: Add `DROP TRIGGER IF EXISTS` before `CREATE TRIGGER`

Add `op.execute("DROP TRIGGER IF EXISTS usuarios_set_updated_at ON usuarios;")` immediately before the `CREATE TRIGGER` statement.

**Pros:** Works on older PostgreSQL versions
**Cons:** Slightly more verbose; the drop+create is not atomic
**Effort:** 2 minutes
**Risk:** Very low

## Recommended Action

Option 1: change line 41 of migration 0005 to `CREATE OR REPLACE TRIGGER`. Single-character change, zero risk on PG 16.

## Technical Details

**Affected files:**
- `alembic/versions/0005_auth_db_constraints_and_updated_at_trigger.py:41`

## Acceptance Criteria

- [ ] `CREATE TRIGGER` replaced with `CREATE OR REPLACE TRIGGER` in migration 0005
- [ ] Running `alembic upgrade head` twice against the same DB does not raise an error
- [ ] `make test` passes

## Work Log

### 2026-03-26 - Identified during ce-review

**By:** Claude Code (ce-review)

**Actions:**
- data-migration-expert flagged as medium-risk CI concern
- Confirmed: line 41 uses plain `CREATE TRIGGER` while line 32 uses `CREATE OR REPLACE FUNCTION`
