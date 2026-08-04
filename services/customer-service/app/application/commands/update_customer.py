"""Use case: cap nhat thong tin lien he cua khach hang (co optimistic
concurrency qua resourceVersion/If-Match)."""
from typing import Optional

from app.domain.entities import Customer
from app.domain.exceptions import CustomerNotFoundError
from app.repositories.interfaces import CustomerRepository


def update_customer(
    repo: CustomerRepository,
    customer_id: str,
    expected_version: int,
    name: Optional[str] = None,
    email: Optional[str] = None,
    phone: Optional[str] = None,
) -> Customer:
    customer = repo.get(customer_id)
    if customer is None:
        raise CustomerNotFoundError(customer_id)
    customer.update_contact(name=name, email=email, phone=phone)
    repo.update(customer, expected_version=expected_version)
    return customer
