"""FastAPI dependency injection - noi duy nhat quyet dinh dang dung
repository/store implementation nao."""
from app.infrastructure.database.repositories import (
    PostgresCustomerRepository,
    PostgresIdempotencyStore,
)
from app.repositories.interfaces import CustomerRepository, IdempotencyStore

_repository = PostgresCustomerRepository()
_idempotency_store = PostgresIdempotencyStore()


def get_repository() -> CustomerRepository:
    return _repository


def get_idempotency_store() -> IdempotencyStore:
    return _idempotency_store
