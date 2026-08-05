"""FastAPI dependency injection - noi duy nhat quyet dinh dang dung
repository implementation nao. App that luon dung PostgresCustomerRepository;
InMemoryCustomerRepository chi con duoc tests/unit tu import truc tiep."""

from app.infrastructure.database.repositories import PostgresCustomerRepository
from app.repositories.interfaces import CustomerRepository

_repository = PostgresCustomerRepository()


def get_repository() -> CustomerRepository:
    return _repository
