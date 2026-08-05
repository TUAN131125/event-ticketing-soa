"""Bounded authentication metric helpers."""

from app.domain.exceptions import IdentityError
from app.observability.metrics import AUTH_EVENTS


def record_success(event: str) -> None:
    AUTH_EVENTS.labels(event, "success").inc()


def record_failure(event: str, error: IdentityError) -> None:
    AUTH_EVENTS.labels(event, error.code).inc()
