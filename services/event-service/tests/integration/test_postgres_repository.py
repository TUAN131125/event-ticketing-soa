"""Integration test - can PostgreSQL that dang chay (xem conftest.py).
Chay bang: pytest tests/integration -m integration
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.domain.entities import Event
from app.domain.enums import EventStatus
from app.domain.exceptions import VersionConflictError
from app.domain.value_objects import Money, TicketType
from app.infrastructure.database.repositories import (
    PostgresAuditRepository,
    PostgresEventRepository,
    PostgresIdempotencyRepository,
)

pytestmark = pytest.mark.integration

NOW = datetime(2026, 8, 1, tzinfo=timezone.utc)


def _event(event_id="EV001") -> Event:
    return Event.create(
        event_id, "Hoi cho cong nghe", "SECC Quan 7",
        starts_at=NOW + timedelta(days=30),
        sale_starts_at=NOW,
        sale_ends_at=NOW + timedelta(days=29),
        ticket_types=[
            TicketType("VIP", "VIP", Money(2000000, "VND")),
            TicketType("STANDARD", "Standard", Money(700000, "VND")),
        ],
    )


def test_next_id_increments_via_db_sequence(postgres_repo: PostgresEventRepository):
    assert postgres_repo.next_id() == "EV001"
    assert postgres_repo.next_id() == "EV002"


def test_add_and_get_round_trip_with_money_ticket_types(postgres_repo: PostgresEventRepository):
    postgres_repo.add(_event())
    fetched = postgres_repo.get("EV001")
    assert fetched is not None
    assert fetched.resource_version == 1
    prices = {t.code: (t.price.amount_minor, t.price.currency) for t in fetched.ticket_types}
    assert prices == {"VIP": (2000000, "VND"), "STANDARD": (700000, "VND")}


def test_get_missing_returns_none(postgres_repo: PostgresEventRepository):
    assert postgres_repo.get("EV999") is None


def test_update_with_correct_version_bumps_resource_version(postgres_repo: PostgresEventRepository):
    postgres_repo.add(_event())
    event = postgres_repo.get("EV001")
    event.status = EventStatus.ON_SALE
    updated = postgres_repo.update(event, expected_version=1)
    assert updated.resource_version == 2

    fetched = postgres_repo.get("EV001")
    assert fetched.status == EventStatus.ON_SALE
    assert fetched.resource_version == 2


def test_update_with_stale_version_raises_conflict(postgres_repo: PostgresEventRepository):
    postgres_repo.add(_event())
    event = postgres_repo.get("EV001")
    with pytest.raises(VersionConflictError):
        postgres_repo.update(event, expected_version=99)


def test_data_survives_new_engine_connection(postgres_repo: PostgresEventRepository):
    from app.infrastructure.database.session import dispose_engine

    postgres_repo.add(_event())
    dispose_engine()

    fresh_repo = PostgresEventRepository()
    fetched = fresh_repo.get("EV001")
    assert fetched is not None
    assert len(fetched.ticket_types) == 2


def test_list_filters_by_status_and_paginates(postgres_repo: PostgresEventRepository):
    for i in range(3):
        postgres_repo.add(_event(f"EV{i + 1:03d}"))
    events, total = postgres_repo.list(status=EventStatus.DRAFT, page=1, page_size=2)
    assert total == 3
    assert len(events) == 2

    events, total = postgres_repo.list(status=None, page=1, page_size=10)
    assert total == 3


def test_audit_records_persist(postgres_repo: PostgresEventRepository):
    audit_repo = PostgresAuditRepository()
    postgres_repo.add(_event())
    audit_repo.record("EV001", "admin", "EVT-01:CREATE")
    audit_repo.record("EV001", "admin", "EVT-07:PUBLISH")

    records = list(audit_repo.list_for_event("EV001"))
    assert [r["action"] for r in records] == ["EVT-01:CREATE", "EVT-07:PUBLISH"]


def test_idempotency_key_replay_returns_same_cached_response(postgres_repo: PostgresEventRepository):
    idem_repo = PostgresIdempotencyRepository()
    assert idem_repo.get("create:key-1") is None

    idem_repo.save("create:key-1", "hash-a", 201, {"eventId": "EV001"})
    cached = idem_repo.get("create:key-1")
    assert cached == ("hash-a", 201, {"eventId": "EV001"})


def test_cascade_delete_removes_ticket_types_with_event(postgres_repo: PostgresEventRepository):
    from sqlalchemy import text

    from app.infrastructure.database.session import session_scope

    postgres_repo.add(_event())
    with session_scope() as session:
        session.execute(text("DELETE FROM event.events WHERE id = 'EV001'"))
    with session_scope() as session:
        remaining = session.execute(
            text("SELECT count(*) FROM event.ticket_types WHERE event_id = 'EV001'")
        ).scalar_one()
    assert remaining == 0
