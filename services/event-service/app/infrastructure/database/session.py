"""Quan ly vong doi engine va session SQLAlchemy ket noi PostgreSQL that."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from threading import Lock

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, get_settings

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None
_engine_lock = Lock()


def get_engine(settings: Settings | None = None) -> Engine:
    global _engine, _session_factory
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                current = settings or get_settings()
                _engine = create_engine(
                    current.database_url,
                    isolation_level="READ COMMITTED",
                    pool_pre_ping=True,
                    pool_size=current.db_pool_size,
                    max_overflow=current.db_max_overflow,
                    pool_recycle=1800,
                    echo=current.sql_echo,
                )
                _session_factory = sessionmaker(
                    bind=_engine,
                    class_=Session,
                    expire_on_commit=False,
                    autoflush=False,
                )
    return _engine


def get_session_factory(settings: Settings | None = None) -> sessionmaker[Session]:
    get_engine(settings)
    if _session_factory is None:
        raise RuntimeError("Session factory chua duoc khoi tao")
    return _session_factory


@contextmanager
def session_scope(settings: Settings | None = None) -> Iterator[Session]:
    """Mo mot session cho 1 don vi cong viec (unit of work), tu commit/rollback."""
    session = get_session_factory(settings)()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def database_ready(settings: Settings | None = None) -> bool:
    """Dung cho /health/ready: kiem tra ket noi DB va da chay migration chua."""
    try:
        with get_engine(settings).connect() as connection:
            connection.execute(text("SELECT 1"))
            version = connection.execute(
                text(
                    "SELECT version_num FROM public.alembic_version "
                    "ORDER BY version_num DESC LIMIT 1"
                )
            ).scalar_one_or_none()
            return version is not None
    except Exception:
        return False


def dispose_engine() -> None:
    global _engine, _session_factory
    with _engine_lock:
        if _engine is not None:
            _engine.dispose()
        _engine = None
        _session_factory = None
