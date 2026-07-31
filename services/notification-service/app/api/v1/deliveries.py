"""Xem lai lich su gui thong bao - huu ich khi demo/tra cuu."""
from fastapi import APIRouter, Depends

from app.application.queries.list_deliveries import list_deliveries
from app.dependencies import get_repository
from app.repositories.interfaces import DeliveryRepository
from app.schemas.responses import DeliveryResponse

router = APIRouter(tags=["deliveries"])


@router.get("/deliveries", response_model=list[DeliveryResponse])
def deliveries(repo: DeliveryRepository = Depends(get_repository)):
    return [DeliveryResponse.from_entity(d) for d in list_deliveries(repo)]
