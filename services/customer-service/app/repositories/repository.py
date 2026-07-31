"""Re-export tien loi: noi khac trong code chi can `from app.repositories
import repository` la co ca interface lan cac implementation dang dung."""
from app.infrastructure.database.repositories import (
    InMemoryCustomerRepository,
    PostgresCustomerRepository,
)
from app.repositories.interfaces import CustomerRepository

__all__ = [
    "CustomerRepository",
    "InMemoryCustomerRepository",
    "PostgresCustomerRepository",
]
