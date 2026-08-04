"""Use case: NOT-07 GetDeliveryStatus - GET /deliveries/{id}."""
from app.domain.entities import Delivery
from app.domain.exceptions import DeliveryNotFoundError
from app.repositories.interfaces import EventDeliveryRepository


def get_delivery(repo: EventDeliveryRepository, delivery_id: str) -> Delivery:
    delivery = repo.get_delivery(delivery_id)
    if delivery is None:
        raise DeliveryNotFoundError(delivery_id)
    return delivery
