"""Use case: liet ke lich su delivery (GET /deliveries)."""
from typing import Iterable

from app.domain.entities import Delivery
from app.repositories.interfaces import EventDeliveryRepository


def list_deliveries(repo: EventDeliveryRepository) -> Iterable[Delivery]:
    return repo.list_deliveries()
