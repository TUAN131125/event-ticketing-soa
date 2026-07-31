"""Endpoint danh cho quan tri - vo hieu hoa khach hang."""
from fastapi import APIRouter, Depends

from app.application.commands.deactivate_customer import deactivate_customer
from app.dependencies import get_repository
from app.repositories.interfaces import CustomerRepository
from app.schemas.responses import CustomerResponse

router = APIRouter(prefix="/customers", tags=["admin"])


@router.post("/{customer_id}/deactivate", response_model=CustomerResponse)
def deactivate(customer_id: str, repo: CustomerRepository = Depends(get_repository)):
    customer = deactivate_customer(repo, customer_id)
    return CustomerResponse.from_entity(customer)
