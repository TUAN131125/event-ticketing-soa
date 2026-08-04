"""Use case: cap nhat consent (dong y nhan thong bao) theo tung kenh.
Endpoint: POST /customers/{id}/consents."""
from app.domain.entities import Customer
from app.domain.enums import ConsentChannel
from app.domain.exceptions import CustomerNotFoundError
from app.repositories.interfaces import CustomerRepository


def update_consent(
    repo: CustomerRepository, customer_id: str, channel: ConsentChannel, granted: bool
) -> Customer:
    customer = repo.get(customer_id)
    if customer is None:
        raise CustomerNotFoundError(customer_id)
    repo.set_consent(customer_id, channel, granted)
    return customer
