"""Canonical Customer lifecycle command endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Path, Response
from libs.platform_http import etag

from app.api.v1.resources import _version
from app.application.commands.deactivate_customer import deactivate_customer
from app.dependencies import get_repository
from app.middleware.authentication import require_service_principal
from app.repositories.interfaces import CustomerRepository
from app.schemas.responses import CustomerResponse

router = APIRouter(
    prefix="/customers",
    tags=["customer-commands"],
    dependencies=[Depends(require_service_principal)],
)


@router.post(
    "/{customerId}/deactivate",
    response_model=CustomerResponse,
    operation_id="deactivateCustomer",
)
def deactivate(
    customer_id: Annotated[str, Path(alias="customerId")],
    response: Response,
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=8, max_length=128)
    ],
    if_match: Annotated[str, Header(alias="If-Match", pattern=r'^"[1-9][0-9]*"$')],
    repo: CustomerRepository = Depends(get_repository),
) -> CustomerResponse:
    customer = deactivate_customer(repo, customer_id, _version(if_match))
    response.headers["ETag"] = etag(customer.resource_version)
    return CustomerResponse.from_entity(customer)
