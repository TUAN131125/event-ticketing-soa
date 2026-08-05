"""Use case: tim khach hang theo email (dung cho Notification Service/ESB)."""

from app.domain.entities import Customer
from app.repositories.interfaces import CustomerRepository


def find_customer_by_email(repo: CustomerRepository, email: str) -> Customer | None:
    return repo.get_by_email(email)
