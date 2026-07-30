"""PostgreSQL engine and transaction lifecycle."""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings

HEAD_REVISION = "0001_identity"


@lru_cache(maxsize=8)
def _engine_for(database_url: str, pool_size: int, max_overflow: int) -> Engine:
    return create_engine(
        database_url,
        pool_pre_ping=True,
        pool_size=pool_size,
        max_overflow=max_overflow,
        isolation_level="READ COMMITTED",
        connect_args={"connect_timeout": 5},
    )


def get_engine(settings: Settings) -> Engine:
    return _engine_for(
        settings.database_url, settings.db_pool_size, settings.db_max_overflow
    )


@lru_cache(maxsize=8)
def _factory_for(
    database_url: str, pool_size: int, max_overflow: int
) -> sessionmaker[Session]:
    return sessionmaker(
        bind=_engine_for(database_url, pool_size, max_overflow),
        expire_on_commit=False,
        autoflush=False,
    )


def get_session_factory(settings: Settings) -> sessionmaker[Session]:
    return _factory_for(
        settings.database_url, settings.db_pool_size, settings.db_max_overflow
    )


def database_ready(settings: Settings) -> bool:
    try:
        with get_engine(settings).connect() as connection:
            connection.execute(text("SELECT 1"))
            revision = connection.scalar(
                text("SELECT version_num FROM alembic_version LIMIT 1")
            )
            identity_table = connection.scalar(
                text("SELECT to_regclass('identity.users')")
            )
            return revision == HEAD_REVISION and identity_table is not None
    except Exception:
        return False


def dispose_engine(settings: Settings) -> None:
    get_engine(settings).dispose()
