from __future__ import annotations

import json
import time
from types import SimpleNamespace

import pytest

from app.api.router import checkin
from app.api.schemas import CheckInRequest
from app.domain.errors import EsbError
from app.domain.models import Principal


class Auth:
    async def verify(self, authorization):
        assert authorization == "Bearer staff-token"
        return Principal("staff-1", frozenset({"CHECKIN_STAFF"}))


class Limiter:
    async def check(self, *args):
        return None


class Ticket:
    def __init__(self, validated_ticket_id="ticket-1"):
        self.validated_ticket_id = validated_ticket_id
        self.validate_calls = []
        self.checkin_calls = []

    async def validate(self, payload, key, ctx):
        self.validate_calls.append((payload, key, ctx))
        return {
            "ticketId": self.validated_ticket_id,
            "bookingId": "booking-1",
            "eventId": "event-1",
            "customerId": "customer-1",
            "seatId": "A1",
            "status": "ISSUED",
            "resourceVersion": 4,
        }

    async def check_in(self, ticket_id, payload, headers, ctx):
        self.checkin_calls.append((ticket_id, payload, headers, ctx))
        return {
            "ticketId": ticket_id,
            "bookingId": "booking-1",
            "eventId": "event-1",
            "customerId": "customer-1",
            "seatId": "A1",
            "status": "CHECKED_IN",
            "resourceVersion": 5,
        }


class Queries:
    async def staff_ticket_projection(self, ticket, ctx, include_qr):
        return {
            "ticketId": ticket["ticketId"],
            "bookingId": ticket["bookingId"],
            "eventId": ticket["eventId"],
            "eventName": "Summer Show",
            "venue": "Hall A",
            "startsAt": "2027-06-01T12:00:00Z",
            "seatId": ticket["seatId"],
            "seatCode": ticket["seatId"],
            "ticketTypeName": "Standard",
            "status": ticket["status"],
            "correlationId": ctx.correlation_id,
            "resourceVersion": ticket["resourceVersion"],
        }


def request(ticket):
    container = SimpleNamespace(
        auth=Auth(),
        limiter=Limiter(),
        ticket=ticket,
        queries=Queries(),
    )
    return SimpleNamespace(
        headers={"Authorization": "Bearer staff-token"},
        state=SimpleNamespace(
            correlation_id="corr-checkin",
            trace_id="a" * 32,
            deadline=time.monotonic() + 10,
        ),
        app=SimpleNamespace(
            state=SimpleNamespace(
                container=container,
                settings=SimpleNamespace(
                    checkin_rate_limit=20,
                    rate_limit_window_seconds=60,
                ),
            )
        ),
    )


@pytest.mark.asyncio
async def test_checkin_revalidates_qr_before_atomic_ticket_command():
    ticket = Ticket()
    response = await checkin(
        "ticket-1",
        CheckInRequest(qrToken="q" * 16),
        request(ticket),
        "idem-checkin-1",
        '"4"',
    )
    payload = json.loads(response.body)
    assert payload["ticket"]["status"] == "CHECKED_IN"
    assert response.headers["etag"] == '"5"'
    assert len(ticket.validate_calls) == 1
    assert len(ticket.checkin_calls) == 1
    assert ticket.checkin_calls[0][2]["If-Match"] == '"4"'


@pytest.mark.asyncio
async def test_checkin_rejects_qr_for_another_ticket_before_mutation():
    ticket = Ticket(validated_ticket_id="ticket-2")
    with pytest.raises(EsbError) as raised:
        await checkin(
            "ticket-1",
            CheckInRequest(qrToken="q" * 16),
            request(ticket),
            "idem-checkin-2",
            '"4"',
        )
    assert raised.value.code == "QR_TICKET_MISMATCH"
    assert ticket.checkin_calls == []
