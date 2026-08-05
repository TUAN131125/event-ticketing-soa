"""Use case: cap nhat thong tin lien he cua khach hang."""

from app.domain.entities import Customer
from app.domain.exceptions import CustomerNotFoundError
from app.repositories.interfaces import CustomerRepository


def update_customer(
    repo: CustomerRepository,
    customer_id: str,
    name: str | None = None,
    email: str | None = None,
    phone: str | None = None,
) -> Customer:
    customer = repo.get(customer_id)
    if customer is None:
        raise CustomerNotFoundError(customer_id)
    customer.update_contact(name=name, email=email, phone=phone)
    repo.update(customer)
    return customer
