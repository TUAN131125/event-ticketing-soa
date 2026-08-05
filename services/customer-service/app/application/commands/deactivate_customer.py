"""Use case: vo hieu hoa khach hang (xoa mem, khong xoa du lieu that)."""

from app.domain.entities import Customer
from app.domain.exceptions import CustomerNotFoundError, PreconditionFailedError
from app.repositories.interfaces import CustomerRepository


def deactivate_customer(
    repo: CustomerRepository, customer_id: str, expected_version: int | None = None
) -> Customer:
    customer = repo.get(customer_id)
    if customer is None:
        raise CustomerNotFoundError(customer_id)
    if expected_version is not None and customer.resource_version != expected_version:
        raise PreconditionFailedError("Customer resource version does not match")
    customer.deactivate()
    repo.update(customer)
    return customer
