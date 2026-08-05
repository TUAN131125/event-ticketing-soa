from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from libs.platform_security import sign_hmac_request

from app.adapters.rest.base import RestClient
from app.contract_freeze import EXPECTED_CATALOG_SHA, EXPECTED_FREEZE_ID
from app.domain.models import Money, RequestContext
from app.resilience.policies import RetryClass


class CustomerRestAdapter:
    contract = (
        "customer-service",
        "customer-service.yaml",
        EXPECTED_FREEZE_ID,
        EXPECTED_CATALOG_SHA,
    )

    def __init__(self, client: RestClient) -> None:
        self.client = client

    async def resolve_mapping(self, identity_subject: str, context: RequestContext) -> Mapping[str, Any]:
        return await self.client.request(
            "GET",
            f"/internal/identity-mappings/{identity_subject}",
            context,
            retry_class=RetryClass.SAFE_READ,
        )

    async def get_customer(self, customer_id: str, context: RequestContext) -> Mapping[str, Any]:
        return await self.client.request(
            "GET",
            f"/customers/{customer_id}",
            context,
            retry_class=RetryClass.SAFE_READ,
        )


class EventRestAdapter:
    contract = (
        "event-service",
        "event-service.yaml",
        EXPECTED_FREEZE_ID,
        EXPECTED_CATALOG_SHA,
    )

    def __init__(self, client: RestClient) -> None:
        self.client = client

    async def list_events(self, context: RequestContext) -> Sequence[Mapping[str, Any]]:
        return await self.client.request("GET", "/events", context, retry_class=RetryClass.SAFE_READ)

    async def get_event(self, event_id: str, context: RequestContext) -> Mapping[str, Any]:
        return await self.client.request("GET", f"/events/{event_id}", context, retry_class=RetryClass.SAFE_READ)

    async def get_sale_eligibility(self, event_id: str, context: RequestContext) -> Mapping[str, Any]:
        return await self.client.request(
            "GET",
            f"/events/{event_id}/sale-eligibility",
            context,
            retry_class=RetryClass.SAFE_READ,
        )


class BookingRestAdapter:
    contract = (
        "booking-service",
        "booking-service.yaml",
        EXPECTED_FREEZE_ID,
        EXPECTED_CATALOG_SHA,
    )

    def __init__(self, client: RestClient) -> None:
        self.client = client
        self._versions: dict[str, int] = {}

    async def create_booking(
        self,
        payload: Mapping[str, Any],
        idempotency_key: str,
        context: RequestContext,
    ) -> Mapping[str, Any]:
        result = await self.client.request(
            "POST",
            "/bookings",
            context,
            json_body=payload,
            idempotency_key=idempotency_key,
            retry_class=RetryClass.IDEMPOTENT_COMMAND,
            ambiguous_command=True,
        )
        self._remember(result)
        return result

    async def get_booking(self, booking_id: str, context: RequestContext) -> Mapping[str, Any]:
        result = await self.client.request(
            "GET",
            f"/bookings/{booking_id}",
            context,
            retry_class=RetryClass.SAFE_READ,
        )
        self._remember(result)
        self._versions.setdefault(booking_id, int(result.get("resourceVersion", 1)))
        return result

    async def decide_access(self, booking_id: str, context: RequestContext) -> Mapping[str, Any]:
        return await self.client.request(
            "POST",
            f"/internal/bookings/{booking_id}/access-decisions",
            context,
            json_body={
                "identitySubject": context.principal.subject,
                "roles": list(context.principal.roles),
            },
            retry_class=RetryClass.SAFE_READ,
        )

    async def transition(
        self,
        operation: str,
        booking_id: str,
        payload: Mapping[str, Any],
        idempotency_key: str,
        context: RequestContext,
    ) -> Mapping[str, Any]:
        suffix = {
            "bookingReservation": "reservation",
            "bookingPaymentStarted": "payment-started",
            "bookingPaymentResult": "payment-result",
            "bookingTickets": "tickets",
            "bookingConfirm": "confirm",
            "bookingFail": "fail",
            "bookingCancel": "cancel",
        }[operation]
        if booking_id not in self._versions:
            await self.get_booking(booking_id, context)
        result = await self.client.request(
            "POST",
            f"/bookings/{booking_id}/{suffix}",
            context,
            json_body=payload,
            idempotency_key=idempotency_key,
            extra_headers={"If-Match": f'"{self._versions[booking_id]}"'},
            retry_class=RetryClass.IDEMPOTENT_COMMAND,
            ambiguous_command=True,
        )
        self._remember(result)
        return result

    def _remember(self, booking: Mapping[str, Any]) -> None:
        booking_id = booking.get("bookingId")
        version = booking.get("resourceVersion")
        if isinstance(booking_id, str) and isinstance(version, int):
            self._versions[booking_id] = version


class PaymentRestAdapter:
    contract = (
        "payment-service",
        "payment-service.yaml",
        EXPECTED_FREEZE_ID,
        EXPECTED_CATALOG_SHA,
    )

    def __init__(self, client: RestClient) -> None:
        self.client = client
        self._versions: dict[str, int] = {}

    async def create_payment(
        self,
        booking_id: str,
        amount: Money,
        method_token: str,
        idempotency_key: str,
        context: RequestContext,
    ) -> Mapping[str, Any]:
        result = await self.client.request(
            "POST",
            "/payments",
            context,
            json_body={
                "bookingId": booking_id,
                "amount": amount.as_wire(),
                "methodToken": method_token,
            },
            idempotency_key=idempotency_key,
            retry_class=RetryClass.IDEMPOTENT_COMMAND,
        )
        self._remember(result)
        return result

    async def get_payment(self, payment_id: str, context: RequestContext) -> Mapping[str, Any]:
        result = await self.client.request("GET", f"/payments/{payment_id}", context, retry_class=RetryClass.SAFE_READ)
        self._remember(result)
        self._versions.setdefault(payment_id, int(result.get("resourceVersion", 1)))
        return result

    async def command(
        self,
        operation: str,
        payment_id: str,
        payload: Mapping[str, Any],
        idempotency_key: str,
        context: RequestContext,
    ) -> Mapping[str, Any]:
        suffix = {
            "authorizePayment": "authorize",
            "capturePayment": "capture",
            "cancelPayment": "cancel",
            "createRefund": "refunds",
            "reconcilePayment": "reconcile",
        }[operation]
        ambiguous = operation in {"authorizePayment", "capturePayment"}
        retry = RetryClass.RECONCILIATION_ONLY if ambiguous else RetryClass.IDEMPOTENT_COMMAND
        if payment_id not in self._versions:
            await self.get_payment(payment_id, context)
        result = await self.client.request(
            "POST",
            f"/payments/{payment_id}/{suffix}",
            context,
            json_body=payload or None,
            idempotency_key=idempotency_key,
            extra_headers={"If-Match": f'"{self._versions[payment_id]}"'},
            retry_class=retry,
            ambiguous_command=ambiguous,
        )
        self._remember(result)
        return result

    def _remember(self, payment: Mapping[str, Any]) -> None:
        payment_id = payment.get("paymentId")
        version = payment.get("resourceVersion")
        if isinstance(payment_id, str) and isinstance(version, int):
            self._versions[payment_id] = version


class TicketRestAdapter:
    contract = (
        "ticket-service",
        "ticket-service.yaml",
        EXPECTED_FREEZE_ID,
        EXPECTED_CATALOG_SHA,
    )

    def __init__(self, client: RestClient) -> None:
        self.client = client
        self._versions: dict[str, int] = {}

    async def issue_tickets(
        self,
        payload: Mapping[str, Any],
        idempotency_key: str,
        context: RequestContext,
    ) -> Sequence[Mapping[str, Any]]:
        result = await self.client.request(
            "POST",
            "/tickets:issue",
            context,
            json_body=payload,
            idempotency_key=idempotency_key,
            retry_class=RetryClass.IDEMPOTENT_COMMAND,
        )
        for ticket in result:
            self._remember(ticket)
        return result

    async def list_booking_tickets(self, booking_id: str, context: RequestContext) -> Sequence[Mapping[str, Any]]:
        result = await self.client.request(
            "GET",
            f"/bookings/{booking_id}/tickets",
            context,
            retry_class=RetryClass.SAFE_READ,
        )
        for ticket in result:
            self._remember(ticket)
        return result

    async def cancel_ticket(self, ticket_id: str, idempotency_key: str, context: RequestContext) -> Mapping[str, Any]:
        if ticket_id not in self._versions:
            ticket = await self.client.request("GET", f"/tickets/{ticket_id}", context, retry_class=RetryClass.SAFE_READ)
            self._remember(ticket)
            self._versions.setdefault(ticket_id, int(ticket.get("resourceVersion", 1)))
        result = await self.client.request(
            "POST",
            f"/tickets/{ticket_id}/cancel",
            context,
            idempotency_key=idempotency_key,
            extra_headers={"If-Match": f'"{self._versions[ticket_id]}"'},
            retry_class=RetryClass.IDEMPOTENT_COMMAND,
        )
        self._remember(result)
        return result

    def _remember(self, ticket: Mapping[str, Any]) -> None:
        ticket_id = ticket.get("ticketId")
        version = ticket.get("resourceVersion")
        if isinstance(ticket_id, str) and isinstance(version, int):
            self._versions[ticket_id] = version


class NotificationRestAdapter:
    contract = (
        "notification-service",
        "notification-service.yaml",
        EXPECTED_FREEZE_ID,
        EXPECTED_CATALOG_SHA,
    )

    def __init__(self, client: RestClient, secret: str) -> None:
        self.client, self.secret = client, secret.encode()

    async def publish(self, payload: Mapping[str, Any], message_id: str, context: RequestContext) -> None:
        timestamp = datetime.now(timezone.utc).isoformat()
        body = {
            "eventId": message_id,
            "eventType": "booking.confirmed",
            "schemaVersion": 1,
            "occurredAt": datetime.now(timezone.utc).isoformat(),
            "correlationId": context.correlation_id,
            "aggregateId": payload.get("bookingId"),
            "data": dict(payload),
        }
        raw = json.dumps(body, separators=(",", ":"), sort_keys=True).encode()
        signature = sign_hmac_request(self.secret, timestamp, raw)
        await self.client.request(
            "POST",
            "/webhooks/events",
            context,
            raw_body=raw,
            retry_class=RetryClass.SIDE_EFFECT,
            extra_headers={
                "Content-Type": "application/json",
                "X-Webhook-Timestamp": timestamp,
                "X-Webhook-Signature": f"sha256={signature}",
            },
        )


class RealtimeRestAdapter:
    contract = (
        "realtime-service",
        "realtime-service.openapi.yaml",
        EXPECTED_FREEZE_ID,
        EXPECTED_CATALOG_SHA,
    )

    def __init__(self, client: RestClient) -> None:
        self.client = client

    async def publish(self, payload: Mapping[str, Any], message_id: str, context: RequestContext) -> None:
        body = {
            "messageId": message_id,
            "bookingId": payload["bookingId"],
            "status": payload["status"],
            "sequence": int(payload.get("sequence", 1)),
            "occurredAt": datetime.now(timezone.utc).isoformat(),
            "correlationId": context.correlation_id,
            "message": "Booking status updated",
        }
        await self.client.request(
            "POST",
            "/internal/status-events",
            context,
            json_body=body,
            retry_class=RetryClass.SIDE_EFFECT,
        )
