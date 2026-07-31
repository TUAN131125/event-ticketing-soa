"""Xem lai lich su gui thong bao - huu ich khi demo/tra cuu."""
from fastapi import APIRouter, Depends

from app.dependencies import get_delivery_log
from app.repositories.interfaces import DeliveryLogRepository

router = APIRouter(tags=["deliveries"])


@router.get("/deliveries")
def list_deliveries(delivery_log: DeliveryLogRepository = Depends(get_delivery_log)):
    return list(delivery_log.list_all())
