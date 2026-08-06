from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from datetime import datetime, timezone
from typing import Any

from app.domain.models import Principal, RequestContext

from .base import RestClient


class CustomerAdapter:
    def __init__(self, client: RestClient) -> None:
        self.client = client

    async def resolve_identity(
        self, subject: str, ctx: RequestContext
    ) -> dict[str, Any]:
        return await self.client.request(
            "GET",
            f"/internal/identity-mappings/{subject}",
            ctx,
            idempotent=True,
        )

    async def get(self, customer_id: str, ctx: RequestContext) -> dict[str, Any]:
        return await self.client.request(
            "GET", f"/customers/{customer_id}", ctx, idempotent=True
        )

    async def create(
        self, payload: dict[str, Any], key: str, ctx: RequestContext
    ) -> dict[str, Any]:
        return await self.client.request(
            "POST",
            "/customers",
            ctx,
            json=payload,
            headers={"Idempotency-Key": key},
            idempotent=True,
        )

    async def replace(
        self,
        customer_id: str,
        payload: dict[str, Any],
        key: str,
        if_match: str,
        ctx: RequestContext,
    ) -> dict[str, Any]:
        return await self.client.request(
            "PUT",
            f"/customers/{customer_id}",
            ctx,
            json=payload,
            headers={"Idempotency-Key": key, "If-Match": if_match},
            idempotent=True,
        )

    async def link_identity(
        self,
        customer_id: str,
        subject: str,
        key: str,
        if_match: str,
        ctx: RequestContext,
    ) -> dict[str, Any]:
        return await self.client.request(
            "PUT",
            f"/internal/customers/{customer_id}/identity-link",
            ctx,
            json={"identitySubject": subject},
            headers={"Idempotency-Key": key, "If-Match": if_match},
            idempotent=True,
        )

    async def update_consent(
        self,
        customer_id: str,
        payload: dict[str, Any],
        key: str,
        if_match: str,
        ctx: RequestContext,
    ) -> dict[str, Any]:
        return await self.client.request(
            "POST",
            f"/customers/{customer_id}/consents",
            ctx,
            json=payload,
            headers={"Idempotency-Key": key, "If-Match": if_match},
            idempotent=True,
        )


class EventAdapter:
    COMMANDS = {
        "create": ("POST", "/events"),
        "replace": ("PUT", "/events/{event_id}"),
        "publish": ("POST", "/events/{event_id}/publish"),
        "pause": ("POST", "/events/{event_id}/pause"),
        "close": ("POST", "/events/{event_id}/close"),
        "cancel": ("POST", "/events/{event_id}/cancel"),
    }

    def __init__(self, client: RestClient) -> None:
        self.client = client

    async def list_events(
        self, params: dict[str, Any], ctx: RequestContext
    ) -> Any:
        return await self.client.request(
            "GET",
            "/events",
            ctx,
            params=params,
            idempotent=True,
        )

    async def get_event(
        self, event_id: str, ctx: RequestContext
    ) -> dict[str, Any]:
        return await self.client.request(
            "GET",
            f"/events/{event_id}",
            ctx,
            idempotent=True,
        )

    async def check_sale_eligibility(
        self, event_id: str, ctx: RequestContext
    ) -> dict[str, Any]:
        return await self.client.request(
            "GET",
            f"/events/{event_id}/sale-eligibility",
            ctx,
            idempotent=True,
        )

    async def admin_command(
        self,
        operation: str,
        event_id: str | None,
        payload: dict[str, Any],
        headers: dict[str, str],
        ctx: RequestContext,
    ) -> Any:
        method, template = self.COMMANDS[operation]
        path = template.format(event_id=event_id)
        return await self.client.request(
            method,
            path,
            ctx,
            json=payload or None,
            headers=headers,
            idempotent=True,
        )


class BookingAdapter:
    def __init__(self, client: RestClient) -> None:
        self.client = client

    async def create(
        self, payload: dict[str, Any], key: str, ctx: RequestContext
    ) -> dict[str, Any]:
        return await self.client.request(
            "POST",
            "/bookings",
            ctx,
            json=payload,
            headers={"Idempotency-Key": key},
            idempotent=True,
        )

    async def get(
        self, booking_id: str, ctx: RequestContext
    ) -> dict[str, Any]:
        return await self.client.request(
            "GET",
            f"/bookings/{booking_id}",
            ctx,
            idempotent=True,
        )

    async def list_customer(
        self,
        customer_id: str,
        params: dict[str, Any],
        ctx: RequestContext,
    ) -> Any:
        return await self.client.request(
            "GET",
            "/bookings",
            ctx,
            params={"customerId": customer_id, **params},
            idempotent=True,
        )

    async def _post(
        self,
        booking_id: str,
        suffix: str,
        payload: dict[str, Any],
        key: str,
        ctx: RequestContext,
    ) -> dict[str, Any]:
        return await self.client.request(
            "POST",
            f"/bookings/{booking_id}/{suffix}",
            ctx,
            json=payload,
            headers={"Idempotency-Key": key},
            idempotent=True,
        )

    async def attach_reservation(self, booking_id, payload, key, ctx):
        return await self._post(booking_id, "reservation", payload, key, ctx)

    async def confirm_reservation(self, booking_id, payload, key, ctx):
        return await self._post(
            booking_id,
            "reservation-confirmed",
            payload,
            key,
            ctx,
        )

    async def start_payment(self, booking_id, payload, key, ctx):
        return await self._post(booking_id, "payment-started", payload, key, ctx)

    async def record_payment(self, booking_id, payload, key, ctx):
        return await self._post(booking_id, "payment-result", payload, key, ctx)

    async def attach_tickets(self, booking_id, payload, key, ctx):
        return await self._post(booking_id, "tickets", payload, key, ctx)

    async def confirm(self, booking_id, payload, key, ctx):
        return await self._post(booking_id, "confirm", payload, key, ctx)

    async def fail(self, booking_id, payload, key, ctx):
        return await self._post(booking_id, "fail", payload, key, ctx)

    async def cancel(self, booking_id, payload, key, ctx):
        return await self._post(booking_id, "cancel", payload, key, ctx)

    async def record_compensation(self, booking_id, payload, key, ctx):
        return await self._post(
            booking_id,
            "compensation-result",
            payload,
            key,
            ctx,
        )


class PaymentAdapter:
    def __init__(self, client: RestClient) -> None:
        self.client = client

    async def create(self, payload, key, ctx):
        return await self.client.request(
            "POST",
            "/payments",
            ctx,
            json=payload,
            headers={"Idempotency-Key": key},
            idempotent=True,
        )

    async def _post(self, payment_id, suffix, payload, key, ctx):
        return await self.client.request(
            "POST",
            f"/payments/{payment_id}/{suffix}",
            ctx,
            json=payload,
            headers={"Idempotency-Key": key},
            idempotent=True,
        )

    async def authorize(self, payment_id, payload, key, ctx):
        return await self._post(payment_id, "authorize", payload, key, ctx)

    async def capture(self, payment_id, payload, key, ctx):
        return await self._post(payment_id, "capture", payload, key, ctx)

    async def get(self, payment_id, ctx):
        return await self.client.request(
            "GET",
            f"/payments/{payment_id}",
            ctx,
            idempotent=True,
        )

    async def cancel(self, payment_id, payload, key, ctx):
        return await self._post(payment_id, "cancel", payload, key, ctx)

    async def refund(self, payment_id, payload, key, ctx):
        # Keep the canonical additive endpoint while the refactored Payment Service
        # still preserves the legacy /refund operation.
        return await self.client.request(
            "POST",
            f"/payments/{payment_id}/refunds",
            ctx,
            json=payload,
            headers={"Idempotency-Key": key},
            idempotent=True,
        )

    async def reconcile(self, payment_id, payload, key, ctx):
        return await self._post(payment_id, "reconcile", payload, key, ctx)


class TicketAdapter:
    def __init__(self, client: RestClient) -> None:
        self.client = client

    async def issue(self, payload, key, ctx):
        return await self.client.request(
            "POST",
            "/tickets:issue",
            ctx,
            json=payload,
            headers={"Idempotency-Key": key},
            idempotent=True,
        )

    async def get(self, ticket_id, ctx):
        return await self.client.request(
            "GET",
            f"/tickets/{ticket_id}",
            ctx,
            idempotent=True,
        )

    async def list_booking(self, booking_id, ctx):
        return await self.client.request(
            "GET",
            f"/bookings/{booking_id}/tickets",
            ctx,
            idempotent=True,
        )

    async def validate(self, payload, key, ctx):
        return await self.client.request(
            "POST",
            "/tickets/validate",
            ctx,
            json=payload,
            headers={"Idempotency-Key": key},
            idempotent=True,
        )

    async def check_in(self, ticket_id, payload, headers, ctx):
        del payload
        return await self.client.request(
            "POST",
            f"/tickets/{ticket_id}/check-in",
            ctx,
            headers=headers,
            idempotent=True,
        )

    async def cancel(self, ticket_id, payload, key, ctx):
        expected_version = payload.get("expectedVersion")
        if expected_version is None:
            ticket = await self.get(ticket_id, ctx)
            expected_version = ticket.get("resourceVersion")
        return await self.client.request(
            "POST",
            f"/tickets/{ticket_id}/cancel",
            ctx,
            headers={
                "Idempotency-Key": key,
                "If-Match": f'"{expected_version}"',
            },
            idempotent=True,
        )


class RealtimeAdapter:
    def __init__(self, client: RestClient) -> None:
        self.client = client

    async def issue_ticket(self, payload, ctx):
        return await self.client.request(
            "POST",
            "/internal/ws-tickets",
            ctx,
            json=payload,
            idempotent=True,
        )



class _OutboxSubscriberBase:
    def __init__(self, client: RestClient) -> None:
        self.client = client

    @staticmethod
    def _context(payload: dict[str, Any], ctx: RequestContext | None) -> RequestContext:
        if ctx is not None:
            return ctx
        trace_id = str(payload.get("traceId") or "")
        if len(trace_id) != 32 or set(trace_id) == {"0"}:
            trace_id = secrets.token_hex(16)
        return RequestContext(
            correlation_id=str(payload.get("correlationId") or "outbox"),
            trace_id=trace_id,
            deadline_monotonic=time.monotonic() + 10,
            principal=Principal("booking-orchestrator", frozenset({"SYSTEM"})),
        )


class NotificationWebhookSubscriber(_OutboxSubscriberBase):
    """Publishes canonical Notification webhook envelopes with HMAC authentication."""

    def __init__(self, client: RestClient, secret: str) -> None:
        super().__init__(client)
        self._secret = secret.encode("utf-8")

    async def publish(
        self,
        topic: str,
        payload: dict[str, Any],
        message_id: str,
        ctx: RequestContext | None = None,
    ) -> None:
        context = self._context(payload, ctx)
        occurred_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        body = {
            "eventId": message_id,
            "eventType": topic,
            "schemaVersion": 1,
            "occurredAt": occurred_at,
            "correlationId": context.correlation_id,
            "aggregateId": str(payload.get("bookingId") or payload.get("aggregateId")),
            "data": payload,
        }
        raw = json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8")
        timestamp = occurred_at
        signature = hmac.new(
            self._secret,
            timestamp.encode("utf-8") + b"." + raw,
            hashlib.sha256,
        ).hexdigest()
        await self.client.request(
            "POST",
            "/webhooks/events",
            context,
            content=raw,
            headers={
                "Content-Type": "application/json",
                "X-Webhook-Timestamp": timestamp,
                "X-Webhook-Signature": f"sha256={signature}",
            },
            idempotent=False,
        )


class RealtimeStatusSubscriber(_OutboxSubscriberBase):
    async def publish(
        self,
        topic: str,
        payload: dict[str, Any],
        message_id: str,
        ctx: RequestContext | None = None,
    ) -> None:
        del topic
        context = self._context(payload, ctx)
        body = {
            "messageId": message_id,
            "bookingId": payload["bookingId"],
            "status": payload["status"],
            "sequence": int(payload.get("sequence", 1)),
            "occurredAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "correlationId": context.correlation_id,
            "message": "Booking status updated",
        }
        await self.client.request(
            "POST",
            "/internal/status-events",
            context,
            json=body,
            idempotent=False,
        )
