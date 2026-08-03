"""Bounded retries for safe PostgreSQL transaction failures."""

from __future__ import annotations

import secrets
import time
from collections.abc import Callable

from sqlalchemy.exc import DBAPIError
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError
from sqlalchemy.orm import Session, sessionmaker

from app.domain.exceptions import DependencyUnavailable, PaymentError

RETRYABLE_SQLSTATES = {"40001", "40P01"}
JITTER = secrets.SystemRandom()


def postgres_sqlstate(error: BaseException) -> str | None:
    current: BaseException | None = error
    while current is not None:
        value = getattr(current, "sqlstate", None) or getattr(current, "pgcode", None)
        if value:
            return str(value)
        current = current.__cause__ or current.__context__
    return None


def execute_database_operation[T](
    sessions: sessionmaker[Session],
    operation: Callable[[Session], T],
    *,
    max_retries: int = 1,
) -> T:
    attempt = 0
    while True:
        try:
            with sessions() as session:
                return operation(session)
        except PaymentError:
            raise
        except DBAPIError as exc:
            if postgres_sqlstate(exc) in RETRYABLE_SQLSTATES and attempt < max_retries:
                attempt += 1
                time.sleep(0.025 * attempt + JITTER.uniform(0.0, 0.025))
                continue
            raise DependencyUnavailable() from exc
        except SQLAlchemyTimeoutError as exc:
            raise DependencyUnavailable() from exc
