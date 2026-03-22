---
status: complete
priority: p2
issue_id: "016"
tags: [code-review, alembic, migrations, python, quality]
dependencies: [013]
---

# Alembic env.py quality fixes: sys.path, compare_type, URL validation, make migrate

## Problem Statement

Four small but independently-reportable issues in the Alembic environment setup. Each is a low-effort fix that prevents a silent failure or confusion in the migration workflow.

## Findings

### 1. Redundant `sys.path.insert` in `alembic/env.py` (flagged by 3 agents)

**Location:** `alembic/env.py:3-12`

`alembic.ini` already sets `prepend_sys_path = .`, which causes Alembic to prepend the project root to `sys.path` before loading `env.py`. The manual `sys.path.insert` in `env.py` is redundant — it does the same thing one step later, using `os.path` string manipulation that will silently return a wrong path if Alembic is invoked from a subdirectory. The `import os` becomes unused once this line is removed.

Fix:
```python
# Remove these lines from alembic/env.py:
import os  # becomes unused
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
```

### 2. Missing `compare_type=True` in `context.configure()` calls (flagged by 2 agents)

**Location:** `alembic/env.py:38-43` and `alembic/env.py:55-57`

Without `compare_type=True`, `alembic revision --autogenerate` will not detect column type changes — only added/removed columns. Since Phase 4 plans to change `documento_id` from `String(36)` to `UUID`, and may alter other column types, this flag is critical for autogenerate to produce correct migrations.

Fix:
```python
# In run_migrations_offline():
context.configure(
    url=url,
    target_metadata=target_metadata,
    literal_binds=True,
    dialect_opts={"paramstyle": "named"},
    compare_type=True,
)

# In run_migrations_online():
context.configure(
    connection=connection,
    target_metadata=target_metadata,
    compare_type=True,
)
```

### 3. Fragile `sync_database_url` derivation — silent no-op on unexpected URL format

**Location:** `api/config.py:12-14`

```python
return self.database_url.replace("+asyncpg", "+psycopg2")
```

If `DATABASE_URL` is set without `+asyncpg` (bare `postgresql://` is valid), this returns the URL unchanged and Alembic will silently attempt to use asyncpg as its sync driver, producing a confusing runtime error deep inside SQLAlchemy rather than a clear startup error.

Fix:
```python
@computed_field
@property
def sync_database_url(self) -> str:
    """Synchronous DB URL for Alembic (psycopg2 instead of asyncpg)."""
    if "+asyncpg" not in self.database_url:
        raise ValueError(
            f"DATABASE_URL must use the +asyncpg scheme; got: {self.database_url!r}"
        )
    return self.database_url.replace("+asyncpg", "+psycopg2")
```

### 4. `make migrate` runs in `api` service, not `migrator` service

**Location:** `Makefile:61`

```makefile
migrate:
    docker compose run --rm -e PYTHONPATH=/app api alembic upgrade head
```

This invokes Alembic inside the `api` container, which is correct but uses a different code path than the `migrator` service used by `docker compose up`. If a future migration has a side effect or relies on a migrator-specific env var, the two paths will silently diverge.

Fix:
```makefile
migrate:
    docker compose run --rm migrator
```

The `migrator` service already has `PYTHONPATH=/app` set in its environment.

## Acceptance Criteria

- [ ] `sys.path.insert` and unused `import os` removed from `alembic/env.py`
- [ ] `compare_type=True` added to both `context.configure()` calls in `env.py`
- [ ] `sync_database_url` raises `ValueError` with a clear message when URL lacks `+asyncpg`
- [ ] `make migrate` runs the `migrator` service, not the `api` service
- [ ] All 59 unit tests pass

## Work Log

- 2026-03-22: sys.path flagged by kieran-python-reviewer (P2-3), code-simplicity-reviewer (P2), architecture-strategist (P2); compare_type by data-migration-expert (P3) and security-sentinel (P3); URL validation by kieran-python-reviewer (P2-1); make migrate by architecture-strategist (P3 — elevated here)
