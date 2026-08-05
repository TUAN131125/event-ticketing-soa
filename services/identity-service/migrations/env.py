"""Alembic environment for Identity Service.

Usage:
    alembic -x db=local upgrade head
    alembic -x db=test upgrade head

The database URL is selected from:
    local -> IDENTITY_DATABASE_URL
    test  -> IDENTITY_TEST_DATABASE_URL
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.infrastructure.database.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_database_target() -> str:
    """Return the requested database target: local or test."""
    arguments = context.get_x_argument(as_dictionary=True)
    target = arguments.get("db", "local").strip().lower()

    allowed_targets = {"local", "test"}

    if target not in allowed_targets:
        allowed = ", ".join(sorted(allowed_targets))
        raise ValueError(
            f"Invalid Alembic database target: {target!r}. Allowed values: {allowed}."
        )

    return target


def get_database_url() -> str:
    """Resolve the database URL for the selected target."""
    target = get_database_target()
    variable_name = (
        "IDENTITY_TEST_DATABASE_URL" if target == "test" else "IDENTITY_DATABASE_URL"
    )
    database_url = os.getenv(variable_name, "").strip()

    if not database_url:
        raise RuntimeError(f"Database URL is empty. Configure {variable_name}.")

    return database_url


database_target = get_database_target()
database_url = get_database_url()

# ConfigParser interprets % as interpolation syntax, so it must be escaped.
config.set_main_option(
    "sqlalchemy.url",
    database_url.replace("%", "%%"),
)

print(
    f"[Alembic] Target database: {database_target} "
    f"({database_url.rsplit('/', maxsplit=1)[-1]})"
)


def run_migrations_offline() -> None:
    """Run migrations without creating a database connection."""
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_schemas=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations using a live PostgreSQL connection."""
    connectable = create_engine(
        database_url,
        poolclass=pool.NullPool,
    )

    try:
        with connectable.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                compare_type=True,
                include_schemas=True,
            )

            with context.begin_transaction():
                context.run_migrations()
    finally:
        connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
