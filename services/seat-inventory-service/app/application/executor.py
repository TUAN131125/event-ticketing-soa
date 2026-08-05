"""Database operation executor with bounded transient retry."""

from __future__ import annotations

import random
import time
from collections.abc import Callable

from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.config import Settings
from app.domain.exceptions import DependencyUnavailable, SeatInventoryError
from app.infrastructure.database.session import session_scope

RETRYABLE_SQLSTATES = {"40001", "40P01"}
TRANSIENT_SQLSTATES = RETRYABLE_SQLSTATES | {"55P03", "08000", "08003", "08006"}


def postgres_sqlstate(error: BaseException) -> str | None:
    current: BaseException | None = error
    while current is not None:
        sqlstate = getattr(current, "sqlstate", None) or getattr(
            current, "pgcode", None
        )
        if sqlstate:
            return str(sqlstate)
        current = current.__cause__ or current.__context__
    return None


def is_retryable_database_error(error: BaseException) -> bool:
    return postgres_sqlstate(error) in TRANSIENT_SQLSTATES


def execute_database_operation[T](
    settings: Settings,
    operation: Callable[[Session], T],
    *,
    max_retries: int = 1,
) -> T:
    attempt = 0
    while True:
        try:
            with session_scope(settings) as session:
                return operation(session)
        except SeatInventoryError:
            raise
        except DBAPIError as exc:
            sqlstate = postgres_sqlstate(exc)
            if sqlstate in RETRYABLE_SQLSTATES and attempt < max_retries:
                attempt += 1
                time.sleep(
                    0.025 * attempt + random.uniform(0.0, 0.025)  # nosec B311
                )
                continue
            raise DependencyUnavailable() from exc
