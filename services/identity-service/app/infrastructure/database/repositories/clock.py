"""Database-backed clock helpers."""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session


def database_now(session: Session) -> datetime:
    value = session.scalar(select(func.clock_timestamp()))
    if not isinstance(value, datetime):
        raise RuntimeError("Database clock is unavailable")
    return value
