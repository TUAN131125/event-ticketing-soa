"""Unit test cho use case (application layer), dung InMemoryEventRepository
+ InMemoryAuditRepository de chay nhanh, khong can PostgreSQL."""
from datetime import datetime, timedelta, timezone

import pytest

from app.application.commands.cancel_event import cancel_event
from app.application.commands.create_event import create_event
from app.application.commands.get_event import get_event
from app.application.commands.get_sale_eligibility import get_sale_eligibility
from app.application.commands.list_events import list_events
from app.application.commands.pause_event import pause_event
from app.application.commands.publish_event import publish_event
from app.application.commands.replace_event import replace_event
from app.domain.enums import EventStatus
from app.domain.exceptions import (
    EventNotFoundError,
    InvalidEventDataError,
    InvalidStateTransitionError,
    VersionConflictError,
)
from app.domain.value_objects import Money, TicketType
from app.infrastructure.database.repositories import InMemoryAuditRepository, InMemoryEventRepository

NOW = datetime(2026, 8, 1, tzinfo=timezone.utc)


@pytest.fixture
def repo() -> InMemoryEventRepository:
    return InMemoryEventRepository()


@pytest.fixture
def audit() -> InMemoryAuditRepository:
    return InMemoryAuditRepository()


def _dates(days_ahead: int = 30):
    starts_at = NOW + timedelta(days=days_ahead)
    sale_starts_at = NOW
    sale_ends_at = starts_at - timedelta(hours=1)
    return starts_at, sale_starts_at, sale_ends_at


def test_seed_event_exists_and_on_sale(repo):
    event = get_event(repo, "EV001")
    assert event.status == EventStatus.ON_SALE
    assert len(event.ticket_types) == 2
    assert event.resource_version == 1


def test_get_missing_event_raises(repo):
    with pytest.raises(EventNotFoundError):
        get_event(repo, "EV999")


def test_create_event_assigns_incrementing_id_and_draft_status(repo, audit):
    starts_at, sale_starts_at, sale_ends_at = _dates()
    event = create_event(
        repo, audit, "admin", "Hoi thao AI", "Trung tam hoi nghi",
        starts_at, sale_starts_at, sale_ends_at,
        [TicketType("STANDARD", "Ve thuong", Money(100000, "VND"))],
    )
    assert event.id == "EV002"
    assert event.status == EventStatus.DRAFT
    assert event.resource_version == 1
    assert list(audit.list_for_event("EV002"))[0]["action"].startswith("EVT-01")


def test_create_event_rejects_invalid_dates(repo, audit):
    starts_at = NOW + timedelta(days=10)
    with pytest.raises(InvalidEventDataError):
        # saleEndsAt sau startsAt -> vi pham invariant
        create_event(
            repo, audit, "admin", "Show loi", "Dia diem",
            starts_at, NOW, starts_at + timedelta(hours=1),
            [TicketType("VIP", "VIP", Money(100000))],
        )


def test_full_state_machine_happy_path(repo, audit):
    starts_at, sale_starts_at, sale_ends_at = _dates()
    event = create_event(
        repo, audit, "admin", "Show moi", "San khau B",
        starts_at, sale_starts_at, sale_ends_at,
        [TicketType("VIP", "VIP", Money(500000))],
    )
    assert event.status == EventStatus.DRAFT
    assert event.resource_version == 1

    event = publish_event(repo, audit, "admin", event.id, event.resource_version)
    assert event.status == EventStatus.ON_SALE
    assert event.resource_version == 2

    event = pause_event(repo, audit, "admin", event.id, event.resource_version)
    assert event.status == EventStatus.PAUSED
    assert event.resource_version == 3

    event = cancel_event(repo, audit, "admin", event.id, event.resource_version, reason="het cho")
    assert event.status == EventStatus.CANCELLED
    assert event.resource_version == 4


def test_invalid_transition_raises_409_style_error(repo, audit):
    # EV001 dang ON_SALE - khong duoc publish lai tu chinh no.
    with pytest.raises(InvalidStateTransitionError):
        publish_event(repo, audit, "admin", "EV001", 1)


def test_stale_if_match_raises_version_conflict(repo, audit):
    with pytest.raises(VersionConflictError):
        pause_event(repo, audit, "admin", "EV001", expected_version=99)


def test_replace_event_updates_profile_and_bumps_version(repo, audit):
    starts_at, sale_starts_at, sale_ends_at = _dates()
    updated = replace_event(
        repo, audit, "admin", "EV001", expected_version=1,
        name="Ten moi", venue="Dia diem moi",
        starts_at=starts_at, sale_starts_at=sale_starts_at, sale_ends_at=sale_ends_at,
        ticket_types=[TicketType("VIP", "VIP", Money(2000000))],
    )
    assert updated.name == "Ten moi"
    assert updated.resource_version == 2
    assert updated.status == EventStatus.ON_SALE  # replace khong doi status


def test_list_events_filters_by_status_and_paginates(repo, audit):
    starts_at, sale_starts_at, sale_ends_at = _dates()
    for i in range(3):
        create_event(
            repo, audit, "admin", f"Show {i}", "Dia diem",
            starts_at, sale_starts_at, sale_ends_at,
            [TicketType("VIP", "VIP", Money(100000))],
        )
    draft_events, total = list_events(repo, EventStatus.DRAFT, page=1, page_size=2)
    assert total == 3
    assert len(draft_events) == 2

    on_sale_events, on_sale_total = list_events(repo, EventStatus.ON_SALE, page=1, page_size=10)
    assert on_sale_total == 1
    assert on_sale_events[0].id == "EV001"


def test_sale_eligibility_true_when_on_sale_and_within_window(repo):
    result = get_sale_eligibility(repo, "EV001")
    assert result["eligible"] is True
    assert result["reasonCode"] is None


def test_sale_eligibility_false_when_not_on_sale(repo, audit):
    starts_at, sale_starts_at, sale_ends_at = _dates()
    event = create_event(
        repo, audit, "admin", "Draft show", "Dia diem",
        starts_at, sale_starts_at, sale_ends_at,
        [TicketType("VIP", "VIP", Money(100000))],
    )
    result = get_sale_eligibility(repo, event.id)
    assert result["eligible"] is False
    assert result["reasonCode"] == "EVENT_NOT_ON_SALE_STATUS_DRAFT"
