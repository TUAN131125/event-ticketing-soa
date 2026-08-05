"""Unit test cho use case (application layer), dung InMemoryEventRepository
de chay nhanh, khong can PostgreSQL. Test hanh vi nghiep vu thuan tuy -
KHONG test SQL/DB (xem tests/integration cho phan do)."""

import pytest

from app.application.commands.cancel_event import cancel_event
from app.application.commands.close_sales import close_sales
from app.application.commands.create_event import create_event
from app.application.commands.get_event import get_event
from app.application.commands.open_sales import open_sales
from app.application.commands.pause_sales import pause_sales
from app.application.commands.update_event import update_event
from app.domain.enums import EventStatus
from app.domain.exceptions import EventNotFoundError, InvalidStateTransitionError
from app.domain.value_objects import TicketType
from app.infrastructure.database.repositories import InMemoryEventRepository


@pytest.fixture
def repo() -> InMemoryEventRepository:
    return InMemoryEventRepository()


def test_seed_event_exists_and_on_sale(repo: InMemoryEventRepository) -> None:
    event = get_event(repo, "EV001")
    assert event.status == EventStatus.ON_SALE
    assert len(event.ticket_types) == 2


def test_get_missing_event_raises(repo: InMemoryEventRepository) -> None:
    with pytest.raises(EventNotFoundError):
        get_event(repo, "EV999")


def test_create_event_assigns_incrementing_id(repo: InMemoryEventRepository) -> None:
    event = create_event(
        repo,
        "Hoi thao AI",
        "Trung tam hoi nghi",
        "2026-09-15T09:00:00",
        [TicketType("STANDARD", 100000)],
    )
    assert event.id == "EV002"
    assert event.status == EventStatus.DRAFT
    assert repo.get("EV002") is not None


def test_update_event_changes_info_not_status(repo: InMemoryEventRepository) -> None:
    updated = update_event(repo, "EV001", name="Ten moi")
    assert updated.name == "Ten moi"
    assert updated.status == EventStatus.ON_SALE


def test_full_state_machine_happy_path(repo: InMemoryEventRepository) -> None:
    event = create_event(
        repo,
        "Show moi",
        "San khau B",
        "2026-10-01T20:00:00",
        [TicketType("VIP", 500000)],
    )
    assert event.status == EventStatus.DRAFT

    event = open_sales(repo, event.id)
    assert event.status == EventStatus.ON_SALE

    event = pause_sales(repo, event.id)
    assert event.status == EventStatus.PAUSED

    event = close_sales(repo, open_sales(repo, event.id).id)
    assert event.status == EventStatus.CLOSED


def test_invalid_transition_raises_409_style_error(
    repo: InMemoryEventRepository,
) -> None:
    # EV001 dang ON_SALE - khong the "open_sales" lai tu chinh no theo
    # bang ALLOWED_TRANSITIONS (chi DRAFT/PAUSED -> ON_SALE).
    with pytest.raises(InvalidStateTransitionError):
        open_sales(repo, "EV001")


def test_cancel_from_draft_allowed_but_not_from_closed(
    repo: InMemoryEventRepository,
) -> None:
    event = create_event(
        repo,
        "Se huy",
        "Dia diem C",
        "2026-11-01T19:00:00",
        [TicketType("VIP", 100000)],
    )
    cancelled = cancel_event(repo, event.id)
    assert cancelled.status == EventStatus.CANCELLED

    with pytest.raises(InvalidStateTransitionError):
        cancel_event(repo, cancelled.id)
