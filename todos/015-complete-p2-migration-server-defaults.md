---
status: complete
priority: p2
issue_id: "015"
tags: [code-review, alembic, migrations, schema, sqlalchemy]
dependencies: [013, 014]
---

# Add `server_default` for NOT NULL columns that lack DB-level defaults

## Problem Statement

Three columns in the initial schema are `NOT NULL` but have no `server_default` in the migration. Python-level `default=` in `mapped_column()` only fires through the SQLAlchemy ORM — it is invisible to PostgreSQL. Any raw `INSERT` (from psql, a fixture loader, a bulk `execute()`, or a future Alembic data migration) that omits these columns will raise a `NOT NULL` constraint violation at runtime with no helpful error message.

This pattern will proliferate to every future table unless addressed now.

## Findings

### 1. `documentos.estado_render` — `NOT NULL`, no `server_default`
- Migration: `sa.Column("estado_render", sa.String(length=50), nullable=False)` — no `server_default`
- Model: `default="pendiente"` — ORM-only
- Risk: Raw INSERT without estado_render raises `NOT NULL` violation

### 2. `datasets.es_publico` — `NOT NULL`, no `server_default`
- Migration: `sa.Column("es_publico", sa.Boolean(), nullable=False)` — no `server_default`
- Model: `default=False` — ORM-only
- Risk: Raw INSERT without es_publico raises `NOT NULL` violation

### 3. `created_at` / `updated_at` on all tables — `NOT NULL`, no `server_default`
- All timestamp columns are `nullable=False` with Python `default=lambda: datetime.now(UTC)` — ORM-only
- Risk: Lower priority than 1+2 since timestamp columns are almost always set by the ORM, but raw SQL admin fixes and future data migrations will silently fail without them

## Proposed Solutions

### Option A: Add `server_default` to migration and model (Recommended)

**Migration `0001_initial_schema.py`:**
```python
# estado_render
sa.Column("estado_render", sa.String(length=50), nullable=False, server_default="pendiente"),

# es_publico
sa.Column("es_publico", sa.Boolean(), nullable=False, server_default=sa.false()),

# timestamps (all tables)
sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
```

**Models — add `server_default` to each `mapped_column`:**
```python
estado_render: Mapped[str] = mapped_column(
    String(50), default="pendiente", server_default="pendiente", nullable=False
)
es_publico: Mapped[bool] = mapped_column(
    Boolean, default=False, server_default=sa.false(), nullable=False
)
created_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True),
    default=lambda: datetime.now(UTC),
    server_default=sa.text("NOW()"),
    nullable=False,
)
```

- **Pros:** Correct at every insertion path; documents intent clearly
- **Cons:** Minor verbosity in models

### Option B: Leave as ORM-only defaults, rely on discipline

- **Pros:** Less code
- **Cons:** Silent failures on raw inserts; sets a bad pattern for Phase 4 new models

**Recommended:** Option A — fix the existing columns and establish the pattern for all future models.

## Acceptance Criteria

- [ ] `estado_render`, `es_publico` have matching `server_default` in both migration and model
- [ ] `created_at`/`updated_at` on all three tables have `server_default=sa.text("NOW()")`
- [ ] `alembic check` passes
- [ ] All 59 unit tests pass
- [ ] Pattern documented in `AGENTS.md` for future model authors

## Work Log

- 2026-03-22: Flagged as P2 (findings 2, 3) by data-migration-expert in Phase 1 Alembic review
