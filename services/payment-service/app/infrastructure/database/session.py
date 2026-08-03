"""SQLAlchemy engine lifecycle and readiness checks."""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, get_settings


@lru_cache(maxsize=8)
def _engine_for(
    url: str,
    pool_size: int,
    max_overflow: int,
    pool_timeout_seconds: int,
    connect_timeout_seconds: int,
) -> Engine:
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_timeout=pool_timeout_seconds,
        pool_recycle=1_800,
        connect_args={"connect_timeout": connect_timeout_seconds},
    )


def get_engine(settings: Settings | None = None) -> Engine:
    current = settings or get_settings()
    return _engine_for(
        current.database_url,
        current.db_pool_size,
        current.db_max_overflow,
        current.db_pool_timeout_seconds,
        current.db_connect_timeout_seconds,
    )


@lru_cache(maxsize=8)
def _factory_for(
    url: str,
    pool_size: int,
    max_overflow: int,
    pool_timeout_seconds: int,
    connect_timeout_seconds: int,
) -> sessionmaker[Session]:
    return sessionmaker(
        bind=_engine_for(
            url,
            pool_size,
            max_overflow,
            pool_timeout_seconds,
            connect_timeout_seconds,
        ),
        expire_on_commit=False,
        autoflush=False,
    )


def get_session_factory(
    settings: Settings | None = None,
) -> sessionmaker[Session]:
    current = settings or get_settings()
    return _factory_for(
        current.database_url,
        current.db_pool_size,
        current.db_max_overflow,
        current.db_pool_timeout_seconds,
        current.db_connect_timeout_seconds,
    )


def database_ready(settings: Settings | None = None) -> bool:
    try:
        with get_engine(settings).connect() as connection:
            row = connection.execute(
                text(
                    "SELECT to_regclass('payment.payments'), "
                    "to_regclass('payment.refunds'), "
                    "to_regclass('payment.idempotency_records'), "
                    "to_regclass('payment.payment_audit'), "
                    "to_regclass('payment.outbox_events'), "
                    "to_regclass('payment.alembic_version')"
                )
            ).one()
            return all(value is not None for value in row)
    except Exception:
        return False


def dispose_engine(settings: Settings | None = None) -> None:
    get_engine(settings).dispose()
