"""Use case: tim khach hang theo email HOAC phone - dung cho endpoint
GET /customers:lookup (contracts/openapi/customer-service.yaml)."""
from app.domain.entities import Customer
from app.domain.exceptions import CustomerNotFoundError
from app.repositories.interfaces import CustomerRepository


def lookup_customer(
    repo: CustomerRepository, email: str | None, phone: str | None
) -> Customer:
    customer = None
    if email is not None:
        customer = repo.get_by_email(email)
    if customer is None and phone is not None:
        customer = repo.get_by_phone(phone)
    if customer is None:
        raise CustomerNotFoundError(email or phone or "")
    return customer
