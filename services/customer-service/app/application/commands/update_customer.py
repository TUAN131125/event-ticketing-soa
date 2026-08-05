"""Use case: cap nhat thong tin lien he cua khach hang."""

from app.domain.entities import Customer
from app.domain.exceptions import CustomerNotFoundError, PreconditionFailedError
from app.repositories.interfaces import CustomerRepository


def update_customer(
    repo: CustomerRepository,
    customer_id: str,
    name: str | None = None,
    email: str | None = None,
    phone: str | None = None,
    expected_version: int | None = None,
) -> Customer:
    customer = repo.get(customer_id)
    if customer is None:
        raise CustomerNotFoundError(customer_id)
    if expected_version is not None and customer.resource_version != expected_version:
        raise PreconditionFailedError("Customer resource version does not match")
    customer.update_contact(name=name, email=email, phone=phone)
    repo.update(customer)
    return customer
