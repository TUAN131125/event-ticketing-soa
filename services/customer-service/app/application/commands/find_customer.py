"""Use case: tim khach hang theo email (dung cho Notification Service/ESB)."""
from typing import Optional

from app.domain.entities import Customer
from app.repositories.interfaces import CustomerRepository


def find_customer_by_email(repo: CustomerRepository, email: str) -> Optional[Customer]:
    return repo.get_by_email(email)
