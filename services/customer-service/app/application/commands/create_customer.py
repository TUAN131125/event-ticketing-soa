"""Use case: tao khach hang moi."""
from app.domain.entities import Customer
from app.domain.rules import ensure_email_unique
from app.repositories.interfaces import CustomerRepository


def create_customer(repo: CustomerRepository, name: str, email: str, phone: str) -> Customer:
    existing_emails = {c.email for c in repo.list_all()}
    ensure_email_unique(existing_emails, email)

    customer_id = repo.next_id()
    customer = Customer.create(customer_id, name, email, phone)
    repo.add(customer)
    return customer
