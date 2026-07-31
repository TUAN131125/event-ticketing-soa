"""FastAPI dependency injection - noi duy nhat quyet dinh dang dung
repository/provider implementation nao. App that luon dung
PostgresDeliveryRepository; InMemoryDeliveryRepository chi con duoc
tests/unit tu import truc tiep."""
from app.infrastructure.database.repositories import PostgresDeliveryRepository
from app.providers.console_provider import ConsoleEmailProvider
from app.providers.email_provider import EmailProvider
from app.repositories.interfaces import DeliveryRepository

_repository = PostgresDeliveryRepository()
_provider = ConsoleEmailProvider()


def get_repository() -> DeliveryRepository:
    return _repository


def get_provider() -> EmailProvider:
    return _provider
