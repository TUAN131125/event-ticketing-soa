"""Event application tests using the in-memory repository."""

from datetime import UTC, datetime, timedelta

import pytest

from app.application.commands.cancel_event import cancel_event
from app.application.commands.close_event import close_event
from app.application.commands.create_event import create_event
from app.application.commands.get_event import get_event
from app.application.commands.open_sales import open_sales
from app.application.commands.pause_sales import pause_sales
from app.application.commands.update_event import update_event
from app.domain.enums import EventStatus
from app.domain.exceptions import EventNotFoundError, InvalidStateTransitionError
from app.domain.value_objects import Money, TicketType
from app.infrastructure.database.repositories import InMemoryEventRepository


@pytest.fixture
def repo() -> InMemoryEventRepository:
    return InMemoryEventRepository()


def draft_event(repo: InMemoryEventRepository, name: str = "Show moi"):
    now = datetime.now(UTC)
    return create_event(
        repo,
        name,
        "San khau B",
        now + timedelta(days=30),
        now + timedelta(days=1),
        now + timedelta(days=20),
        [TicketType("VIP", "VIP", Money(500_000, "VND"))],
    )


def test_seed_event_exists_and_on_sale(repo: InMemoryEventRepository) -> None:
    event = get_event(repo, "EV001")
    assert event.status == EventStatus.ON_SALE
    assert len(event.ticket_types) == 2


def test_get_missing_event_raises(repo: InMemoryEventRepository) -> None:
    with pytest.raises(EventNotFoundError):
        get_event(repo, "EV999")


def test_create_event_assigns_incrementing_id(repo: InMemoryEventRepository) -> None:
    event = draft_event(repo, "Hoi thao AI")
    assert event.id == "EV002"
    assert event.status == EventStatus.DRAFT
    assert repo.get("EV002") is not None


def test_update_event_changes_info_not_status(repo: InMemoryEventRepository) -> None:
    current = get_event(repo, "EV001")
    updated = update_event(
        repo,
        current.id,
        name="Ten moi",
        venue=current.venue,
        starts_at=current.starts_at,
        sale_starts_at=current.sale_starts_at,
        sale_ends_at=current.sale_ends_at,
        ticket_types=current.ticket_types,
        expected_version=current.resource_version,
    )
    assert updated.name == "Ten moi"
    assert updated.status == EventStatus.ON_SALE


def test_full_state_machine_happy_path(repo: InMemoryEventRepository) -> None:
    event = draft_event(repo)
    assert event.status == EventStatus.DRAFT

    event = open_sales(repo, event.id)
    assert event.status == EventStatus.ON_SALE

    event = pause_sales(repo, event.id)
    assert event.status == EventStatus.PAUSED

    event = open_sales(repo, event.id)
    assert event.status == EventStatus.ON_SALE


def test_invalid_transition_raises_409_style_error(
    repo: InMemoryEventRepository,
) -> None:
    # EV001 dang ON_SALE - khong the "open_sales" lai tu chinh no theo
    # bang ALLOWED_TRANSITIONS (chi DRAFT/PAUSED -> ON_SALE).
    with pytest.raises(InvalidStateTransitionError):
        open_sales(repo, "EV001")


def test_close_ends_event_from_on_sale_and_from_paused(
    repo: InMemoryEventRepository,
) -> None:
    on_sale = open_sales(repo, draft_event(repo, "Ket thuc truc tiep").id)
    assert close_event(repo, on_sale.id).status == EventStatus.ENDED

    paused = pause_sales(repo, open_sales(repo, draft_event(repo, "Tam dung").id).id)
    assert close_event(repo, paused.id).status == EventStatus.ENDED


def test_close_rejects_draft_and_terminal_states(
    repo: InMemoryEventRepository,
) -> None:
    draft = draft_event(repo, "Chua mo ban")
    with pytest.raises(InvalidStateTransitionError):
        close_event(repo, draft.id)

    ended = close_event(repo, open_sales(repo, draft_event(repo, "Da ket thuc").id).id)
    with pytest.raises(InvalidStateTransitionError):
        close_event(repo, ended.id)

    cancelled = cancel_event(repo, draft_event(repo, "Da huy").id)
    with pytest.raises(InvalidStateTransitionError):
        close_event(repo, cancelled.id)


def test_close_rejects_stale_expected_version(repo: InMemoryEventRepository) -> None:
    event = open_sales(repo, draft_event(repo, "Sai version").id)
    with pytest.raises(InvalidStateTransitionError):
        close_event(repo, event.id, event.resource_version + 1)


def test_close_missing_event_raises(repo: InMemoryEventRepository) -> None:
    with pytest.raises(EventNotFoundError):
        close_event(repo, "EV-KHONG-TON-TAI")


def test_cancel_from_draft_allowed_but_not_when_already_cancelled(
    repo: InMemoryEventRepository,
) -> None:
    event = draft_event(repo, "Se huy")
    cancelled = cancel_event(repo, event.id)
    assert cancelled.status == EventStatus.CANCELLED

    with pytest.raises(InvalidStateTransitionError):
        cancel_event(repo, cancelled.id)
