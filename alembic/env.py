from __future__ import annotations

import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# noqa imports — register all models with Base.metadata before autogenerate
import api.models.documento  # noqa: F401
import api.models.ejecucion_error  # noqa: F401
import api.models.dataset  # noqa: F401
import api.models.usuario  # noqa: F401
import api.models.sesion_refresh  # noqa: F401

from api.database import Base
from api.config import settings

# Alembic Config object — gives access to alembic.ini values
config = context.config

# Wire up Python logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set the synchronous URL for Alembic (psycopg2, not asyncpg)
config.set_main_option("sqlalchemy.url", settings.sync_database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (generate SQL without a live connection)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (against a live DB connection)."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
