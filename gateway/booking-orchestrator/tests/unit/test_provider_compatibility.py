"""ESB → Booking/Payment integration guards introduced in wave 4.

Three classes of defect are pinned here:

* a Payment status the orchestrator cannot read must stop the saga, not be treated as a
  decline (which would release seats against possibly-captured money);
* a Booking transition response without resourceVersion must stop the saga, not silently
  reuse the previous version as the next command's expectedVersion;
* owner-scoped queries must use the owner-scoped Booking operation.
"""

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

from app.application.booking import BookingSaga
from app.domain.errors import EsbError
from app.domain.models import Principal, RequestContext
from app.persistence.repositories import InMemoryRepository
from tests.fakes import Booking, Customer, Event, Payment, Seat, Ticket

PAYMENT_SIDE_EFFECTS = {"payment-create", "authorize", "capture"}


def context(name: str) -> RequestContext:
    return RequestContext(
        name, "1" * 32, time.monotonic() + 5, Principal("u", frozenset({"CUSTOMER"}), "cust-1")
    )


def saga(log, *, payment=None, booking=None):
    repo = InMemoryRepository()
    return (
        BookingSaga(
            Customer(),
            Event(),
            Seat(log),
            booking or Booking(log),
            payment or Payment(log),
            Ticket(log),
            repo,
            repo,
            SimpleNamespace(reservation_ttl_seconds=300),
        ),
        repo,
    )


async def place(instance, key: str):
    return await instance.place(
        {"eventId": "e1", "seatIds": ["A1"], "paymentMethodToken": "success"},
        key,
        context(key),
    )


class UnreadableCapturePayment(Payment):
    """Capture answers with a status outside the canonical Payment enum."""

    def __init__(self, log, status: str | None):
        super().__init__(log)
        self.capture_status = status

    async def capture(self, *args):
        self.log.append("capture")
        body = {"resourceVersion": 3}
        if self.capture_status is not None:
            body["status"] = self.capture_status
        return body


class VersionlessBooking(Booking):
    """A transition response that omits resourceVersion."""

    def __init__(self, log, drop_on: str):
        super().__init__(log)
        self.drop_on = drop_on

    async def attach_reservation(self, *args):
        result = await super().attach_reservation(*args)
        if self.drop_on == "reservation":
            result.pop("resourceVersion", None)
        return result


@pytest.mark.parametrize("status", ["DECLINED", "SUCCEEDED", "WEIRD", None])
@pytest.mark.asyncio
async def test_unreadable_capture_status_is_a_protocol_error(status) -> None:
    log: list[str] = []
    instance, _ = saga(log, payment=UnreadableCapturePayment(log, status))

    with pytest.raises(EsbError) as raised:
        await place(instance, f"cap-{status}")

    assert raised.value.code == "PAYMENT_PROTOCOL_ERROR"
    assert raised.value.status_code == 502
    assert raised.value.retryable is False
    # The saga must not have carried on into ticket issuance or confirmation.
    assert "issue-ticket" not in log
    assert "booking-confirm" not in log


@pytest.mark.asyncio
async def test_refunded_capture_status_does_not_look_like_a_decline() -> None:
    """REFUNDED is a real Payment status but not a capture outcome this saga can settle."""
    log: list[str] = []
    instance, _ = saga(log, payment=UnreadableCapturePayment(log, "REFUNDED"))

    with pytest.raises(EsbError) as raised:
        await place(instance, "cap-refunded")

    assert raised.value.code == "PAYMENT_PROTOCOL_ERROR"
    # A decline would have released the seats; a protocol error must not.
    assert "release-seat" not in log
    assert "issue-ticket" not in log


@pytest.mark.asyncio
async def test_missing_resource_version_stops_the_saga() -> None:
    log: list[str] = []
    instance, _ = saga(log, booking=VersionlessBooking(log, "reservation"))

    with pytest.raises(EsbError) as raised:
        await place(instance, "no-version")

    assert raised.value.code == "BOOKING_PROTOCOL_ERROR"
    assert raised.value.status_code == 502
    assert raised.value.retryable is False
    # Nothing may be charged once the orchestrator has lost track of the booking version.
    assert not PAYMENT_SIDE_EFFECTS & set(log)


@pytest.mark.asyncio
async def test_version_advances_across_every_transition() -> None:
    log: list[str] = []
    booking = Booking(log)
    instance, repo = saga(log, booking=booking)

    status, _ = await place(instance, "version-walk")

    assert status == 201
    workflow = next(iter(repo.workflows.values()))
    # The fake bumps resourceVersion on every transition, so the workflow must have ended
    # on the latest one rather than on a version it started with.
    assert workflow.booking_version == booking.v
    assert workflow.booking_version > 1


@pytest.mark.asyncio
async def test_my_bookings_uses_the_owner_scoped_operation() -> None:
    """Recorded against the adapter, so the path is asserted rather than the fake."""
    from app.adapters.rest.providers import BookingAdapter

    seen: dict[str, object] = {}

    class RecordingClient:
        async def request(self, method, path, ctx, **kwargs):
            seen["method"] = method
            seen["path"] = path
            seen["params"] = kwargs.get("params")
            return {"items": [], "page": 1, "pageSize": 20, "total": 0}

    adapter = BookingAdapter(RecordingClient())
    await adapter.list_customer("CUS-1", {"page": 1, "pageSize": 20}, context("mine"))

    assert seen["method"] == "GET"
    assert seen["path"] == "/customers/CUS-1/bookings"
    # customerId is no longer a filter on a broad admin list.
    assert "customerId" not in (seen["params"] or {})
