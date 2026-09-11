"""Alembic environment — resolves the database URL from env vars and
imports all ORM models so Alembic can auto-detect the full schema.
"""
from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import engine_from_config, pool

# Load .env so DATABASE_URL / POSTGRES_* vars are available when running
# alembic from the command line.
load_dotenv(".env", override=True)

# ------------------------------------------------------------------
# Alembic Config object — gives access to alembic.ini values.
# ------------------------------------------------------------------
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ------------------------------------------------------------------
# Import all ORM models so Alembic can see the full metadata.
# ------------------------------------------------------------------
from backend.app.infrastructure.database.base import Base  # noqa: E402
import backend.app.infrastructure.database.models  # noqa: E402, F401  (registers all models)

target_metadata = Base.metadata

# ------------------------------------------------------------------
# Resolve the database URL.
# ------------------------------------------------------------------

def _get_url() -> str:
    from backend.app.infrastructure.database.engine import build_database_url
    return build_database_url()


# ------------------------------------------------------------------
# Offline migration (generate SQL script without a live DB).
# ------------------------------------------------------------------

def run_migrations_offline() -> None:
    url = _get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


# ------------------------------------------------------------------
# Online migration (connect to DB and apply changes).
# ------------------------------------------------------------------

def run_migrations_online() -> None:
    cfg = config.get_section(config.config_ini_section, {})
    cfg["sqlalchemy.url"] = _get_url()

    connectable = engine_from_config(
        cfg,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
