from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)
database_url = os.getenv("ESB_DATABASE_URL", config.get_main_option("sqlalchemy.url") or "").strip()
if not database_url:
    raise RuntimeError("ESB_DATABASE_URL is required for migrations")
config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))

# The ESB persists workflow, outbox and WebSocket-ticket state through explicit
# SQLAlchemy Core tables built inside app.persistence.repositories.PostgresRepository
# rather than a declarative Base. Revisions here are hand-written for that reason, and
# autogenerate is deliberately not wired up: it would try to drop the legacy pre-refactor
# tables that this chain keeps for rollback.
target_metadata = None


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section) or {}, prefix="sqlalchemy.", poolclass=pool.NullPool
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_async_migrations())
