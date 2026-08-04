"""Endpoint danh cho quan tri - vo hieu hoa khach hang. Khop dung
contracts/openapi/customer-service.yaml (deactivateCustomer)."""
from fastapi import APIRouter, Depends, Header, status
from fastapi.responses import JSONResponse

from app.application.commands.deactivate_customer import deactivate_customer
from app.dependencies import get_idempotency_store, get_repository
from app.domain.rules import parse_if_match
from app.repositories.interfaces import CustomerRepository, IdempotencyStore
from app.schemas.responses import CustomerResponse

router = APIRouter(prefix="/customers", tags=["admin"])


@router.post("/{customer_id}/deactivate", response_model=CustomerResponse)
def deactivate(
    customer_id: str,
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
    customer = deactivate_customer(repo, customer_id, expected_version)
    body = CustomerResponse.from_entity(customer)
    idem_store.save(idempotency_key, status.HTTP_200_OK, body.model_dump())
    return body
