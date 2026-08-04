"""NOT-07 GetDeliveryStatus + liet ke + NOT-05/08 RetryDelivery.
Caller chinh: Admin/Ops (Muc 2 dac ta) -> yeu cau Bearer JWT co role
admin hoac ops (xem security/authentication.py)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header

from app.application.commands.retry_delivery import retry_delivery
from app.application.queries.get_delivery import get_delivery
from app.application.queries.list_deliveries import list_deliveries
from app.dependencies import get_event_repository, get_provider, get_template_repository
from app.providers.email_provider import EmailProvider
from app.repositories.interfaces import EventDeliveryRepository, TemplateRepository
from app.schemas.responses import DeliveryResponse
from app.security.authentication import Principal, require_role
from app.security.authorization import OPS_ROLES

router = APIRouter(prefix="/deliveries", tags=["deliveries"])


@router.get("", response_model=list[DeliveryResponse])
def list_all(
    repo: EventDeliveryRepository = Depends(get_event_repository),
    _principal: Principal = Depends(require_role(*OPS_ROLES)),
):
    return [DeliveryResponse.from_entity(d) for d in list_deliveries(repo)]


@router.get("/{delivery_id}", response_model=DeliveryResponse)
def get_one(
    delivery_id: str,
    repo: EventDeliveryRepository = Depends(get_event_repository),
    _principal: Principal = Depends(require_role(*OPS_ROLES)),
):
    return DeliveryResponse.from_entity(get_delivery(repo, delivery_id))


@router.post("/{delivery_id}/retry", status_code=202)
def retry(
    delivery_id: str,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=128),
    event_repo: EventDeliveryRepository = Depends(get_event_repository),
    template_repo: TemplateRepository = Depends(get_template_repository),
    provider: EmailProvider = Depends(get_provider),
    _principal: Principal = Depends(require_role(*OPS_ROLES)),
):
    # Ghi chu ve Idempotency-Key: hop dong bat buoc header nay nhung SQL
    # baseline (Giai doan 5) khong co bang notification.idempotency_records
    # rieng nhu cac schema khac (customer/ticket/esb) - nen o day CHI
    # validate header ton tai (FastAPI tu lam qua Header(...) bat buoc),
    # chua luu so bo idempotency ledger. An toan idempotent thuc te den
    # tu chinh trang thai nghiep vu: retry vao delivery khong o
    # RETRY_PENDING/DEAD_LETTER se bi tu choi 409 (xem domain/rules.py).
    delivery = retry_delivery(event_repo, template_repo, provider, delivery_id)
    return {"deliveryId": delivery.id, "status": delivery.status.value}
