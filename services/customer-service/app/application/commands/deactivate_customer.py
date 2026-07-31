"""Use case: vo hieu hoa khach hang (xoa mem, khong xoa du lieu that)."""
from app.domain.entities import Customer
from app.domain.exceptions import CustomerNotFoundError
from app.repositories.interfaces import CustomerRepository


def deactivate_customer(repo: CustomerRepository, customer_id: str) -> Customer:
    customer = repo.get(customer_id)
    if customer is None:
        raise CustomerNotFoundError(customer_id)
    customer.deactivate()
    repo.update(customer)
    return customer
