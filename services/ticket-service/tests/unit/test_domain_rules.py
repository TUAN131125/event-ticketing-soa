from datetime import UTC, datetime

import pytest

from app.domain.entities import Ticket
from app.domain.enums import TicketStatus
from app.domain.exceptions import (
    InvalidRequest,
    InvalidStateTransition,
    VersionConflict,
)
from app.domain.rules import (
    advisory_lock_id,
    canonical_request_hash,
    normalize_ticket_definitions,
)
from app.domain.value_objects import TicketDefinition


def ticket() -> Ticket:
    return Ticket.issue(
        ticket_id="TKT000000001",
        booking_id="BK00000001",
        customer_id="C001",
        event_id="EV001",
        payment_id="PAY00000001",
        seat_id="A-01",
        seat_label="A-01",
        ticket_type="VIP",
        now=datetime.now(UTC),
    )


def test_issue_creates_a_valid_versioned_ticket() -> None:
    result = ticket()
    assert result.status == TicketStatus.VALID
    assert result.qr_version == 1
    assert result.resource_version == 1


def test_regenerate_qr_rotates_version_without_changing_status() -> None:
    result = ticket()
    result.regenerate_qr(expected_version=1, now=datetime.now(UTC))
    assert result.status == TicketStatus.VALID
    assert result.qr_version == 2
    assert result.resource_version == 2


def test_check_in_is_terminal_and_cannot_be_cancelled() -> None:
    result = ticket()
    result.check_in(
        gate_id="GATE-A",
        checked_in_by="STAFF-1",
        expected_version=1,
        now=datetime.now(UTC),
    )
    assert result.status == TicketStatus.CHECKED_IN
    with pytest.raises(InvalidStateTransition):
        result.cancel(reason="too late", expected_version=2, now=datetime.now(UTC))


def test_cancelled_ticket_cannot_rotate_or_check_in() -> None:
    result = ticket()
    result.cancel(reason="booking refunded", expected_version=1, now=datetime.now(UTC))
    with pytest.raises(InvalidStateTransition):
        result.regenerate_qr(expected_version=2, now=datetime.now(UTC))
    with pytest.raises(InvalidStateTransition):
        result.check_in(
            gate_id="GATE-A",
            checked_in_by="STAFF-1",
            expected_version=2,
            now=datetime.now(UTC),
        )


def test_expected_version_and_ticket_definitions_are_enforced() -> None:
    with pytest.raises(VersionConflict):
        ticket().regenerate_qr(expected_version=9, now=datetime.now(UTC))
    with pytest.raises(InvalidRequest, match="duplicate"):
        normalize_ticket_definitions(
            (
                TicketDefinition("A-01", "A-01", "VIP"),
                TicketDefinition("A-01", "A-01", "VIP"),
            )
        )


def test_definition_order_hash_and_lock_are_deterministic() -> None:
    normalized = normalize_ticket_definitions(
        (
            TicketDefinition("A-02", "A-02", "VIP"),
            TicketDefinition("A-01", "A-01", "STANDARD"),
        )
    )
    assert [value.seat_id for value in normalized] == ["A-01", "A-02"]
    assert canonical_request_hash({"b": 2, "a": 1}) == canonical_request_hash(
        {"a": 1, "b": 2}
    )
    assert advisory_lock_id("IssueTickets", "key-1") == advisory_lock_id(
        "IssueTickets", "key-1"
    )
    assert advisory_lock_id("IssueTickets", "key-1") != advisory_lock_id(
        "IssueTickets", "key-2"
    )
