"""Alembic environment for the payment schema."""

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.infrastructure.database.models import Base

config = context.config
# Alembic stores options in ConfigParser, where percent signs are interpolation
# markers. Preserve percent-encoded database credentials such as "%40".
config.set_main_option(
    "sqlalchemy.url", os.environ["PAYMENT_DATABASE_URL"].replace("%", "%%")
)
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,
        version_table_schema="payment",
    )
    context.execute("CREATE SCHEMA IF NOT EXISTS payment")
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args={
            "connect_timeout": int(os.getenv("PAYMENT_DB_CONNECT_TIMEOUT_SECONDS", "5"))
        },
    )
    with connectable.connect() as connection:
        connection.exec_driver_sql("CREATE SCHEMA IF NOT EXISTS payment")
        connection.commit()
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            version_table_schema="payment",
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
