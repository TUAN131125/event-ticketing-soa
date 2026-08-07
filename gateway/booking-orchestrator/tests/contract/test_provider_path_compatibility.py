"""Every Booking/Payment call the ESB can make must exist in the canonical contract.

The adapters are driven with a recording client so the assertion is made against the URL the
adapter actually builds, not against a hand-maintained list that can drift from the code.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from app.adapters.rest.providers import BookingAdapter, PaymentAdapter

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
CONTRACTS = REPOSITORY_ROOT / "contracts"


class RecordingClient:
    """Captures the method and path an adapter builds without performing any I/O."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def request(self, method, path, ctx, **kwargs):
        self.calls.append((method.upper(), path))
        return {"resourceVersion": 1, "status": "CAPTURED"}


def canonical(document: str) -> dict:
    return yaml.safe_load((CONTRACTS / document).read_text(encoding="utf-8"))


def templates(document: dict) -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    for route, item in document["paths"].items():
        for method in item:
            if method.lower() in {"get", "post", "put", "patch", "delete"}:
                found.add((method.upper(), route))
    return found


def normalise(path: str, concrete: dict[str, str]) -> str:
    """Turn a concrete URL back into its canonical template."""
    for value, placeholder in concrete.items():
        path = re.sub(rf"(?<=/){re.escape(value)}(?=/|$)", placeholder, path)
    return path


BOOKING_IDS = {"BKG-1": "{booking_id}", "CUS-1": "{customer_id}"}
PAYMENT_IDS = {"PAY-1": "{payment_id}"}


async def booking_calls() -> set[tuple[str, str]]:
    client = RecordingClient()
    adapter = BookingAdapter(client)
    ctx = object()
    await adapter.create({}, "k", ctx)
    await adapter.get("BKG-1", ctx)
    await adapter.list_customer("CUS-1", {"page": 1, "pageSize": 20}, ctx)
    for method in (
        adapter.attach_reservation,
        adapter.confirm_reservation,
        adapter.start_payment,
        adapter.record_payment,
        adapter.attach_tickets,
        adapter.confirm,
        adapter.fail,
        adapter.cancel,
        adapter.record_compensation,
    ):
        await method("BKG-1", {}, "k", ctx)
    return {(m, normalise(p, BOOKING_IDS)) for m, p in client.calls}


async def payment_calls() -> set[tuple[str, str]]:
    client = RecordingClient()
    adapter = PaymentAdapter(client)
    ctx = object()
    await adapter.create({}, "k", ctx)
    await adapter.get("PAY-1", ctx)
    for method in (
        adapter.authorize,
        adapter.capture,
        adapter.cancel,
        adapter.refund,
        adapter.reconcile,
    ):
        await method("PAY-1", {}, "k", ctx)
    return {(m, normalise(p, PAYMENT_IDS)) for m, p in client.calls}


@pytest.mark.asyncio
async def test_every_booking_call_exists_in_the_canonical_contract() -> None:
    calls = await booking_calls()
    available = templates(canonical("booking-service.yaml"))
    missing = sorted(calls - available)
    assert not missing, f"ESB calls Booking operations that do not exist: {missing}"


@pytest.mark.asyncio
async def test_every_payment_call_exists_in_the_canonical_contract() -> None:
    calls = await payment_calls()
    available = templates(canonical("payment-service.yaml"))
    missing = sorted(calls - available)
    assert not missing, f"ESB calls Payment operations that do not exist: {missing}"


@pytest.mark.asyncio
async def test_my_bookings_uses_the_owner_scoped_operation() -> None:
    calls = await booking_calls()
    assert ("GET", "/customers/{customer_id}/bookings") in calls
    # The broad admin list must not be the owner-scoped query path.
    assert ("GET", "/bookings") not in calls


@pytest.mark.asyncio
async def test_refund_uses_the_canonical_collection_endpoint() -> None:
    calls = await payment_calls()
    assert ("POST", "/payments/{payment_id}/refunds") in calls
    assert ("POST", "/payments/{payment_id}/refund") not in calls


def test_fakes_do_not_advertise_endpoints_the_adapters_lack() -> None:
    """A fake method with no adapter counterpart lets a saga test pass against nothing."""
    from tests import fakes

    for fake_name, adapter in (("Booking", BookingAdapter), ("Payment", PaymentAdapter)):
        fake = getattr(fakes, fake_name)
        fake_methods = {
            name
            for name in vars(fake)
            if not name.startswith("_") and callable(vars(fake)[name])
        }
        adapter_methods = {
            name for name in vars(adapter) if not name.startswith("_")
        }
        phantom = fake_methods - adapter_methods - {"r"}
        assert not phantom, f"{fake_name} fake exposes {sorted(phantom)} with no adapter"
