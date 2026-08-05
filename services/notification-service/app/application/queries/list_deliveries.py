"""Use case: xem lai lich su gui thong bao - huu ich khi demo/tra cuu."""
from collections.abc import Iterable

from app.domain.entities import Delivery
from app.repositories.interfaces import DeliveryRepository


def list_deliveries(repo: DeliveryRepository) -> Iterable[Delivery]:
    return repo.list_all()
