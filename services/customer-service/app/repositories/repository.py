"""Re-export tien loi: noi khac trong code chi can `from app.repositories
import repository` la co ca interface lan cac implementation dang dung."""
from app.infrastructure.database.repositories import (
    InMemoryCustomerRepository,
    PostgresCustomerRepository,
    PostgresIdempotencyStore,
)
from app.repositories.interfaces import CustomerRepository, IdempotencyStore

__all__ = [
    "CustomerRepository",
    "IdempotencyStore",
    "InMemoryCustomerRepository",
    "PostgresCustomerRepository",
    "PostgresIdempotencyStore",
]
