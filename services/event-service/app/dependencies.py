"""FastAPI dependency injection - noi duy nhat quyet dinh dang dung
repository implementation nao. App that luon dung PostgresEventRepository;
InMemoryEventRepository chi con duoc tests/unit tu import truc tiep."""

from app.infrastructure.database.repositories import PostgresEventRepository
from app.repositories.interfaces import EventRepository

_repository = PostgresEventRepository()


def get_repository() -> EventRepository:
    return _repository
