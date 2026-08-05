"""Canonical delivery queries, retries and template replacement."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Response, status
from libs.platform_http import etag, parse_if_match

from app.dependencies import get_provider, get_repository
from app.domain.entities import NotificationTemplate
from app.domain.enums import DeliveryStatus
from app.middleware.authentication import require_service_principal
from app.providers.email_provider import EmailProvider
from app.repositories.interfaces import DeliveryRepository
from app.schemas.requests import TemplateUpdateRequest
from app.schemas.responses import DeliveryResponse

router = APIRouter(
    tags=["deliveries"], dependencies=[Depends(require_service_principal)]
)


def _version(value: str) -> int:
    try:
        return parse_if_match(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="If-Match is invalid") from exc


@router.get(
    "/deliveries", response_model=list[DeliveryResponse], operation_id="listDeliveries"
)
def deliveries(
    response: Response, repo: DeliveryRepository = Depends(get_repository)
) -> list[DeliveryResponse]:
    items = list(repo.list_all())
    response.headers["ETag"] = etag(
        max((item.resource_version for item in items), default=1)
    )
    return [DeliveryResponse.from_entity(item) for item in items]


@router.get(
    "/deliveries/{deliveryId}",
    response_model=DeliveryResponse,
    operation_id="getDelivery",
)
def get_delivery(
    delivery_id: Annotated[str, Path(alias="deliveryId")],
    response: Response,
    repo: DeliveryRepository = Depends(get_repository),
) -> DeliveryResponse:
    delivery = repo.get(delivery_id)
    if delivery is None:
        raise HTTPException(status_code=404, detail="Delivery not found")
    response.headers["ETag"] = etag(delivery.resource_version)
    return DeliveryResponse.from_entity(delivery)


@router.post(
    "/deliveries/{deliveryId}/retry",
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="retryDelivery",
)
def retry_delivery(
    delivery_id: Annotated[str, Path(alias="deliveryId")],
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=8, max_length=128)
    ],
    if_match: Annotated[str, Header(alias="If-Match", pattern=r'^"[1-9][0-9]*"$')],
    repo: DeliveryRepository = Depends(get_repository),
    provider: EmailProvider = Depends(get_provider),
) -> Response:
    delivery = repo.get(delivery_id)
    if delivery is None:
        raise HTTPException(status_code=404, detail="Delivery not found")
    if delivery.resource_version != _version(if_match):
        raise HTTPException(status_code=412, detail="Delivery version does not match")
    if delivery.status not in {
        DeliveryStatus.RETRY_PENDING,
        DeliveryStatus.DEAD_LETTER,
    }:
        raise HTTPException(status_code=409, detail="Delivery cannot be retried")
    delivery.attempt_count += 1
    delivery.resource_version += 1
    try:
        provider.send(
            to=delivery.to_address,
            subject=delivery.subject,
            body=delivery.body,
        )
        delivery.status = DeliveryStatus.DELIVERED
        delivery.last_error_code = None
    except Exception:  # noqa: BLE001 -- retry state must be persisted
        delivery.status = DeliveryStatus.RETRY_PENDING
        delivery.last_error_code = "PROVIDER_FAILURE"
    repo.update(delivery)
    return Response(status_code=status.HTTP_202_ACCEPTED)


@router.put("/templates/{code}", operation_id="replaceTemplate")
def replace_template(
    code: str,
    payload: TemplateUpdateRequest,
    response: Response,
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=8, max_length=128)
    ],
    if_match: Annotated[str, Header(alias="If-Match", pattern=r'^"[1-9][0-9]*"$')],
    repo: DeliveryRepository = Depends(get_repository),
) -> dict[str, object]:
    current = repo.get_template(code)
    expected = _version(if_match)
    if current is not None and current.resource_version != expected:
        raise HTTPException(status_code=412, detail="Template version does not match")
    if current is None and expected != 1:
        raise HTTPException(status_code=412, detail="New template version must be one")
    template = NotificationTemplate(
        code,
        payload.subject,
        payload.body,
        1 if current is None else current.resource_version + 1,
    )
    repo.save_template(template)
    response.headers["ETag"] = etag(template.resource_version)
    return {
        "code": template.code,
        "subject": template.subject,
        "body": template.body,
        "resourceVersion": template.resource_version,
    }
