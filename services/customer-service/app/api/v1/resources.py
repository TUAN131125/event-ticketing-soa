"""Canonical Customer resource endpoints."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Path,
    Query,
    Response,
    status,
)
from libs.platform_http import etag, parse_if_match

from app.application.commands.create_customer import create_customer
from app.application.commands.get_customer import get_customer
from app.application.commands.update_customer import update_customer
from app.dependencies import get_repository
from app.domain.exceptions import CustomerNotFoundError, PreconditionFailedError
from app.middleware.authentication import require_service_principal
from app.repositories.interfaces import CustomerRepository
from app.schemas.requests import (
    ConsentUpdateRequest,
    CustomerCreateRequest,
    CustomerUpdateRequest,
)
from app.schemas.responses import CustomerResponse

router = APIRouter(
    prefix="/customers",
    tags=["customers"],
    dependencies=[Depends(require_service_principal)],
)


def _version(value: str) -> int:
    try:
        return parse_if_match(value)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail="If-Match is invalid") from exc


@router.post(
    "",
    response_model=CustomerResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="createCustomer",
)
def create(
    payload: CustomerCreateRequest,
    response: Response,
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=8, max_length=128)
    ],
    repo: CustomerRepository = Depends(get_repository),
) -> CustomerResponse:
    customer = create_customer(repo, payload.name, str(payload.email), payload.phone)
    response.headers["ETag"] = etag(customer.resource_version)
    return CustomerResponse.from_entity(customer)


@router.get(":lookup", response_model=CustomerResponse, operation_id="lookupCustomer")
def lookup(
    response: Response,
    email: str | None = Query(default=None),
    phone: str | None = Query(default=None),
    repo: CustomerRepository = Depends(get_repository),
) -> CustomerResponse:
    if bool(email) == bool(phone):
        raise HTTPException(
            status_code=422, detail="Provide exactly one of email or phone"
        )
    customer = repo.get_by_email(email) if email else repo.get_by_phone(phone or "")
    if customer is None:
        raise CustomerNotFoundError(email or phone or "")
    response.headers["ETag"] = etag(customer.resource_version)
    return CustomerResponse.from_entity(customer)


@router.get(
    "/{customerId}", response_model=CustomerResponse, operation_id="getCustomer"
)
def get(
    customer_id: Annotated[str, Path(alias="customerId")],
    response: Response,
    repo: CustomerRepository = Depends(get_repository),
) -> CustomerResponse:
    customer = get_customer(repo, customer_id)
    response.headers["ETag"] = etag(customer.resource_version)
    return CustomerResponse.from_entity(customer)


@router.put(
    "/{customerId}", response_model=CustomerResponse, operation_id="replaceCustomer"
)
def replace(
    customer_id: Annotated[str, Path(alias="customerId")],
    payload: CustomerUpdateRequest,
    response: Response,
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=8, max_length=128)
    ],
    if_match: Annotated[str, Header(alias="If-Match", pattern=r'^"[1-9][0-9]*"$')],
    repo: CustomerRepository = Depends(get_repository),
) -> CustomerResponse:
    customer = update_customer(
        repo,
        customer_id,
        name=payload.name,
        email=str(payload.email),
        phone=payload.phone,
        expected_version=_version(if_match),
    )
    response.headers["ETag"] = etag(customer.resource_version)
    return CustomerResponse.from_entity(customer)


@router.post(
    "/{customerId}/consents",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="updateCustomerConsent",
)
def update_consent(
    customer_id: Annotated[str, Path(alias="customerId")],
    payload: ConsentUpdateRequest,
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=8, max_length=128)
    ],
    if_match: Annotated[str, Header(alias="If-Match", pattern=r'^"[1-9][0-9]*"$')],
    repo: CustomerRepository = Depends(get_repository),
) -> Response:
    customer = get_customer(repo, customer_id)
    if customer.resource_version != _version(if_match):
        raise PreconditionFailedError("Customer resource version does not match")
    repo.save_consent(customer_id, payload.channel, payload.granted)
    customer.resource_version += 1
    customer.updated_at = datetime.now(UTC)
    repo.update(customer)
    return Response(
        status_code=status.HTTP_204_NO_CONTENT,
        headers={"ETag": etag(customer.resource_version)},
    )
