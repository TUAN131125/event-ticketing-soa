"""Re-export tien loi: noi khac trong code chi can `from app.repositories
import repository` la co ca interface lan cac implementation dang dung."""
from app.infrastructure.database.repositories import (
    InMemoryEventDeliveryRepository,
    InMemoryTemplateRepository,
    PostgresEventDeliveryRepository,
    PostgresTemplateRepository,
)
from app.repositories.interfaces import EventDeliveryRepository, TemplateRepository

__all__ = [
    "EventDeliveryRepository",
    "TemplateRepository",
    "InMemoryEventDeliveryRepository",
    "InMemoryTemplateRepository",
    "PostgresEventDeliveryRepository",
    "PostgresTemplateRepository",
]
