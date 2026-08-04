"""REST endpoint cho nghiep vu Customer - khop dung contracts/openapi/
customer-service.yaml. Tang API chi nhan request/tra response + xu ly
Idempotency-Key/If-Match (moi quan tam thuoc giao thuc HTTP), moi logic
nghiep vu thuc su nam o tang application/domain."""
from fastapi import APIRouter, Depends, Header, Query, status
from fastapi.responses import JSONResponse

from app.application.commands.create_customer import create_customer
from app.application.commands.get_customer import get_customer
from app.application.commands.lookup_customer import lookup_customer
from app.application.commands.update_consent import update_consent
from app.application.commands.update_customer import update_customer
from app.dependencies import get_idempotency_store, get_repository
from app.domain.rules import parse_if_match
from app.repositories.interfaces import CustomerRepository, IdempotencyStore
from app.schemas.requests import (
    ConsentUpdateRequest,
    CustomerCreateRequest,
    CustomerUpdateRequest,
)
from app.schemas.responses import CustomerResponse

router = APIRouter(prefix="/customers", tags=["customers"])


def _if_match_header(header_value: str) -> str:
    return header_value


@router.post("", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED)
def create(
    payload: CustomerCreateRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    repo: CustomerRepository = Depends(get_repository),
    idem_store: IdempotencyStore = Depends(get_idempotency_store),
):
    cached = idem_store.get(idempotency_key)
    if cached is not None:
        cached_status, cached_body = cached
        return JSONResponse(status_code=cached_status, content=cached_body)

    customer = create_customer(repo, payload.name, payload.email, payload.phone or "")
    body = CustomerResponse.from_entity(customer)
    idem_store.save(idempotency_key, status.HTTP_201_CREATED, body.model_dump())
    return body


@router.get("/{customer_id}", response_model=CustomerResponse)
def get(customer_id: str, repo: CustomerRepository = Depends(get_repository)):
    customer = get_customer(repo, customer_id)
    return CustomerResponse.from_entity(customer)


@router.get(":lookup", response_model=CustomerResponse)
def lookup(
    email: str | None = Query(default=None),
    phone: str | None = Query(default=None),
    repo: CustomerRepository = Depends(get_repository),
):
    customer = lookup_customer(repo, email=email, phone=phone)
    return CustomerResponse.from_entity(customer)


@router.put("/{customer_id}", response_model=CustomerResponse)
def update(
    customer_id: str,
    payload: CustomerUpdateRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    if_match: str = Header(..., alias="If-Match"),
    repo: CustomerRepository = Depends(get_repository),
    idem_store: IdempotencyStore = Depends(get_idempotency_store),
):
    cached = idem_store.get(idempotency_key)
    if cached is not None:
        cached_status, cached_body = cached
        return JSONResponse(status_code=cached_status, content=cached_body)

    expected_version = parse_if_match(if_match)
    customer = update_customer(
        repo, customer_id, expected_version,
        name=payload.name, email=payload.email, phone=payload.phone,
    )
    body = CustomerResponse.from_entity(customer)
    idem_store.save(idempotency_key, status.HTTP_200_OK, body.model_dump())
    return body


@router.post("/{customer_id}/consents", status_code=status.HTTP_204_NO_CONTENT)
def consents(
    customer_id: str,
    payload: ConsentUpdateRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    repo: CustomerRepository = Depends(get_repository),
    idem_store: IdempotencyStore = Depends(get_idempotency_store),
):
    cached = idem_store.get(idempotency_key)
    if cached is not None:
        cached_status, _ = cached
        return JSONResponse(status_code=cached_status, content=None)

    update_consent(repo, customer_id, payload.channel, payload.granted)
    idem_store.save(idempotency_key, status.HTTP_204_NO_CONTENT, {})
    return JSONResponse(status_code=status.HTTP_204_NO_CONTENT, content=None)


@router.get("/{customer_id}/exists")
def exists(customer_id: str, repo: CustomerRepository = Depends(get_repository)):
    """Endpoint tien loi ngoai contract chuan (khong co trong OpenAPI GD5),
    giu lai de ESB kiem tra nhanh khach hang co ton tai khong ma khong can
    xu ly loi 404 - khong xung dot voi contract that vi la endpoint cong
    them, khong thay the endpoint nao trong spec."""
    return {"exists": repo.get(customer_id) is not None}
