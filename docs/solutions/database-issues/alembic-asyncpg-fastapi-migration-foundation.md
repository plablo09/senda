---
title: "Alembic + asyncpg + FastAPI: Migration Foundation Setup"
category: database-issues
date: 2026-03-22
tags:
  - alembic
  - migrations
  - sqlalchemy
  - asyncpg
  - psycopg2
  - fastapi
  - docker
  - postgresql
severity: high
status: resolved
---

## Problem

`Base.metadata.create_all()` run inside the FastAPI `lifespan` function is an inadequate DDL strategy: it cannot roll back, cannot detect schema drift, and produces no versioned history. The app would call `create_all()` on every container start, making schema evolution invisible and unsafe.

**Observable symptoms:**
- No migration history or version tracking
- Schema changes required editing Python models and restarting containers, with no audit trail
- `alembic check` not available; no way to detect model/DB drift in CI
- `EjecucionError.documento_id` was typed as `String(36)` in the ORM but the FK target (`documentos.id`) was `UUID`, causing type mismatch in autogenerate

---

## Root Cause

FastAPI's async runtime (`asyncpg`) and Alembic's migration runner require **different SQLAlchemy dialects**. Alembic uses synchronous `psycopg2`; the app uses async `asyncpg`. A single `DATABASE_URL` cannot serve both without a translation layer. Without this dual-engine pattern in place, developers reach for `create_all()` as a fallback.

---

## Solution

### 1. Dual-Engine URL Derivation via `computed_field`

Add a `sync_database_url` computed property to Pydantic `Settings` that derives the psycopg2 URL from the async one. This ensures both URLs stay in sync from a single env var.

```python
# api/config.py
from pydantic import computed_field

class Settings(BaseSettings):
    database_url: str  # must use +asyncpg scheme

    @computed_field  # type: ignore[prop-decorator]
    @property
    def sync_database_url(self) -> str:
        if "+asyncpg" not in self.database_url:
            raise ValueError(
                f"DATABASE_URL must use the +asyncpg scheme; got: {self.database_url!r}"
            )
        return self.database_url.replace("+asyncpg", "+psycopg2")
```

### 2. `alembic/env.py` — Import All Models, Use `NullPool`

Alembic must see `Base.metadata` populated with all mapped tables, so every model module must be imported before autogenerate runs.

```python
# alembic/env.py
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context

# --- Import ALL model modules so Base.metadata is populated ---
import api.models.documento      # noqa: F401
import api.models.ejecucion_error  # noqa: F401
import api.models.dataset        # noqa: F401

from api.database import Base
from api.config import settings

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", settings.sync_database_url)
target_metadata = Base.metadata


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,  # one-shot process — no persistent pool
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,  # detect column type changes in autogenerate
        )
        with context.begin_transaction():
            context.run_migrations()
```

**Key decisions:**
- `NullPool`: migrations run in a one-shot process; a connection pool is wasteful and causes hangs
- `compare_type=True`: without this, autogenerate misses column type changes (e.g., `String` → `UUID`)
- No `sys.path.insert()`: `alembic.ini` already sets `prepend_sys_path = .`

### 3. `alembic.ini` — Leave `sqlalchemy.url` Blank

The URL is set programmatically in `env.py`; a non-empty value in `alembic.ini` would shadow it.

```ini
[alembic]
script_location = alembic
prepend_sys_path = .
sqlalchemy.url =
```

### 4. Initial Migration — Use `server_default`, Not Just ORM `default`

ORM `default=` fires only when inserting through SQLAlchemy. Raw SQL inserts, seed scripts, or tools that bypass the ORM will get `NULL` without `server_default`.

```python
# alembic/versions/0001_initial_schema.py
def upgrade() -> None:
    op.create_table(
        "documentos",
        sa.Column("estado_render", sa.String(50), nullable=False,
                  server_default="pendiente"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        ...
    )
    op.create_table(
        "ejecucion_errores",
        sa.Column("documento_id", sa.UUID(), nullable=True),  # UUID, not String(36)
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.ForeignKeyConstraint(["documento_id"], ["documentos.id"],
                                ondelete="SET NULL"),
        ...
    )
```

**FK type consistency:** FK columns referencing `UUID` primary keys must also be `sa.UUID()`, not `sa.String(36)`. PostgreSQL enforces this.

### 5. Docker `migrator` One-Shot Service + `db` Healthcheck

The `api` and `worker` services must not start until both `db` is healthy **and** migrations have completed successfully.

```yaml
# docker-compose.yml (relevant excerpts)
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U senda -d senda"]
      interval: 2s
      timeout: 3s
      retries: 15
      start_period: 10s  # give Postgres time to initialize before retrying

  migrator:
    build: { context: ., dockerfile: docker/Dockerfile.api }
    command: alembic upgrade head
    environment: { PYTHONPATH: /app }
    env_file: .env
    depends_on:
      db: { condition: service_healthy }
    restart: "no"  # one-shot; must not restart on success

  api:
    depends_on:
      db: { condition: service_healthy }
      migrator: { condition: service_completed_successfully }

  worker:
    depends_on:
      db: { condition: service_healthy }
      migrator: { condition: service_completed_successfully }
```

**`service_completed_successfully` vs `service_healthy`:** Use `service_completed_successfully` for one-shot services (migrator). Use `service_healthy` for long-running services (db). If you use `service_healthy` on a one-shot, the gate never unblocks because the service exits before becoming "healthy."

### 6. Copy Alembic Files Into Docker Image

```dockerfile
# docker/Dockerfile.api
COPY alembic.ini .
COPY alembic/ alembic/
```

### 7. Model Conventions — Keep ORM and Migration in Sync

Add both `default=` (ORM) and `server_default=` (DB) to all columns with defaults:

```python
# ORM model pattern
from datetime import datetime, UTC
import sqlalchemy as sa
from sqlalchemy.orm import mapped_column, Mapped
from sqlalchemy import DateTime, String, Boolean

estado_render: Mapped[str] = mapped_column(
    String(50),
    default="pendiente",
    server_default="pendiente",
    nullable=False,
)
created_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True),
    default=lambda: datetime.now(UTC),
    server_default=sa.text("NOW()"),
    nullable=False,
)
es_publico: Mapped[bool] = mapped_column(
    Boolean,
    default=False,
    server_default=sa.false(),
    nullable=False,
)
```

### 8. Delete `create_tables()` Entirely

Once Alembic is in place, `create_all()` is not just redundant — it's dangerous. It can silently create tables that Alembic doesn't know about, causing `alembic check` to fail. Delete the function and its call site.

---

## Pitfalls

| Pitfall | Consequence | Fix |
|---------|-------------|-----|
| Keeping `sys.path.insert(0, ...)` in `env.py` when `prepend_sys_path = .` is in `alembic.ini` | Redundant, fragile | Remove it |
| Omitting `compare_type=True` | Autogenerate misses type changes | Add to `context.configure()` |
| FK column typed `String(36)` pointing at `UUID` PK | Type mismatch, broken FK in PG | Use `sa.UUID()` for FK |
| ORM `default=` without `server_default=` | Raw SQL inserts get `NULL` | Add both |
| `service_healthy` on one-shot `migrator` | `api` never starts | Use `service_completed_successfully` |
| Non-empty `sqlalchemy.url` in `alembic.ini` with URL set in `env.py` | `alembic.ini` value shadows `env.py` | Leave blank in `alembic.ini` |
| Bare `op.drop_table()` in `downgrade()` without `IF EXISTS` | `ProgrammingError: table does not exist` on a database that was stamped but never migrated (e.g., fresh CI environment) | Use `op.execute("DROP TABLE IF EXISTS table_name")` — `op.drop_table()` has no `if_exists` parameter in Alembic's standard API |

---

## Prevention

### Checklist: Adding a New Model

- [ ] New model file imports are added to `alembic/env.py`
- [ ] All columns with defaults have both `default=` (ORM) and `server_default=` (DB)
- [ ] FK columns pointing at `UUID` PKs use `sa.UUID()`, not `String`
- [ ] `DateTime` columns use `DateTime(timezone=True)` consistently
- [ ] Run `make migrate-check` — confirms no pending autogenerate changes

### Checklist: Writing a New Migration

- [ ] Run `make revision MSG="description"` to autogenerate a draft
- [ ] Review the generated file — autogenerate is not perfect
- [ ] Verify `server_default` values match ORM `default` values
- [ ] Verify `downgrade()` reverses `upgrade()` completely
- [ ] Every `drop_table` / `drop_index` / `drop_constraint` in `downgrade()` uses `IF EXISTS` — count them against the operations in `upgrade()` and verify the numbers match (`op.drop_table()` has no `if_exists` param; use `op.execute("DROP TABLE IF EXISTS ...")`)
- [ ] Idempotency check: `alembic upgrade head && alembic downgrade base && alembic upgrade head` — all three must exit 0
- [ ] Run `make migrate` locally to confirm it applies cleanly

### Detection

```bash
# Detect model/DB drift — should output "No new upgrade operations detected."
make migrate-check

# Find FK columns that might be String instead of UUID
grep -r "String(36)" api/models/

# Find DateTime columns missing timezone
grep -r "DateTime()" api/models/  # should return nothing; use DateTime(timezone=True)

# Confirm every model module is imported in env.py
grep "import api.models" alembic/env.py
```

---

## Related

- [`docs/solutions/runtime-errors/docker-compose-stack-startup-failures.md`](../runtime-errors/docker-compose-stack-startup-failures.md) — `service_completed_successfully` pattern and `pg_isready` healthcheck
- [`docs/solutions/runtime-errors/async-python-fastapi-sqlalchemy-impl-pitfalls.md`](../runtime-errors/async-python-fastapi-sqlalchemy-impl-pitfalls.md) — asyncpg vs psycopg2 dialect differences
- [`docs/solutions/test-failures/pytest-asyncio-fixture-scope-alembic-missing-guard-polling-timeout.md`](../test-failures/pytest-asyncio-fixture-scope-alembic-missing-guard-polling-timeout.md) — concrete case study: `op.drop_table()` without `IF EXISTS` on 1 of 3 tables causing fresh-DB downgrade crash (PR #8 code review)
