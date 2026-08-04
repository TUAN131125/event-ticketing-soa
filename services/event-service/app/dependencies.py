"""FastAPI dependency injection - noi duy nhat quyet dinh dang dung
repository implementation nao. App that luon dung cac lop Postgres*;
InMemory* chi con duoc tests/unit tu import truc tiep."""

from app.infrastructure.database.repositories import (
    PostgresAuditRepository,
    PostgresEventRepository,
    PostgresIdempotencyRepository,
)
from app.repositories.interfaces import (
    AuditRepository,
    EventRepository,
    IdempotencyRepository,
)

_repository = PostgresEventRepository()
_idempotency_repository = PostgresIdempotencyRepository()
_audit_repository = PostgresAuditRepository()


def get_repository() -> EventRepository:
    return _repository


def get_idempotency_repository() -> IdempotencyRepository:
    return _idempotency_repository


def get_audit_repository() -> AuditRepository:
    return _audit_repository
