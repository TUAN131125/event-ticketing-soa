"""Use case: lay thong tin 1 khach hang theo id."""

from app.domain.entities import Customer
from app.domain.exceptions import CustomerNotFoundError
from app.repositories.interfaces import CustomerRepository


def get_customer(repo: CustomerRepository, customer_id: str) -> Customer:
    customer = repo.get(customer_id)
    if customer is None:
        raise CustomerNotFoundError(customer_id)
    return customer
