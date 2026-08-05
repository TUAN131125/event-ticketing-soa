"""PostgreSQL persistence checks for the current Delivery aggregate."""

from __future__ import annotations

import pytest

from app.domain.entities import Delivery
from app.domain.exceptions import DuplicateCorrelationError
from app.infrastructure.database.repositories import PostgresDeliveryRepository

pytestmark = pytest.mark.integration


def delivery(delivery_id: str, event_id: str) -> Delivery:
    return Delivery.create(
        delivery_id,
        event_id,
        "customer@example.com",
        "Booking confirmed",
        "Notification body",
    )


def test_add_get_and_unique_event(postgres_repo: PostgresDeliveryRepository) -> None:
    postgres_repo.add(delivery("N000001", "event-1"))
    fetched = postgres_repo.get("N000001")
    assert fetched is not None
    assert fetched.event_id == "event-1"
    with pytest.raises(DuplicateCorrelationError):
        postgres_repo.add(delivery("N000002", "event-1"))


def test_sequence_and_list(postgres_repo: PostgresDeliveryRepository) -> None:
    assert postgres_repo.next_id() == "N000001"
    postgres_repo.add(delivery("N000001", "event-1"))
    assert [item.id for item in postgres_repo.list_all()] == ["N000001"]
