"""FastAPI dependency injection - noi duy nhat quyet dinh dang dung
repository/provider implementation nao. App that luon dung Postgres*;
InMemory* chi con duoc tests/unit tu import truc tiep."""
from app.infrastructure.database.repositories import (
    PostgresEventDeliveryRepository,
    PostgresTemplateRepository,
)
from app.providers.console_provider import ConsoleEmailProvider
from app.providers.email_provider import EmailProvider
from app.repositories.interfaces import EventDeliveryRepository, TemplateRepository

_event_repository = PostgresEventDeliveryRepository()
_template_repository = PostgresTemplateRepository()
_provider = ConsoleEmailProvider()


def get_event_repository() -> EventDeliveryRepository:
    return _event_repository


def get_template_repository() -> TemplateRepository:
    return _template_repository


def get_provider() -> EmailProvider:
    return _provider
