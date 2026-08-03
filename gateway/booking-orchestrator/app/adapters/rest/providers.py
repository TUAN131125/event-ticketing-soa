from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from app.adapters.rest.base import RestClient
from app.contract_freeze import EXPECTED_CATALOG_SHA, EXPECTED_FREEZE_ID
from app.domain.errors import DependencyFailure
from app.domain.models import Money, RequestContext
from app.resilience.policies import RetryClass


class CustomerRestAdapter:
    contract = (
        "openapi.customer-service",
        "openapi/customer-service.yaml",
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
        "openapi.event-service",
        "openapi/event-service.yaml",
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
        "openapi.booking-service",
        "openapi/booking-service.yaml",
        EXPECTED_FREEZE_ID,
        EXPECTED_CATALOG_SHA,
    )

    def __init__(self, client: RestClient) -> None:
        self.client = client

    async def create_booking(self, payload: Mapping[str, Any], idempotency_key: str, context: RequestContext) -> Mapping[str, Any]:
        return await self.client.request(
            "POST",
            "/bookings",
            context,
            json_body=payload,
            idempotency_key=idempotency_key,
            retry_class=RetryClass.IDEMPOTENT_COMMAND,
            ambiguous_command=True,
        )

    async def get_booking(self, booking_id: str, context: RequestContext) -> Mapping[str, Any]:
        return await self.client.request("GET", f"/bookings/{booking_id}", context, retry_class=RetryClass.SAFE_READ)

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
        return await self.client.request(
            "POST",
            f"/bookings/{booking_id}/{suffix}",
            context,
            json_body=payload,
            idempotency_key=idempotency_key,
            retry_class=RetryClass.IDEMPOTENT_COMMAND,
            ambiguous_command=True,
        )


class PaymentRestAdapter:
    contract = (
        "openapi.payment-service",
        "openapi/payment-service.yaml",
        EXPECTED_FREEZE_ID,
        EXPECTED_CATALOG_SHA,
    )

    def __init__(self, client: RestClient) -> None:
        self.client = client

    async def create_payment(
        self,
        booking_id: str,
        amount: Money,
        method_token: str,
        idempotency_key: str,
        context: RequestContext,
    ) -> Mapping[str, Any]:
        return await self.client.request(
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

    async def get_payment(self, payment_id: str, context: RequestContext) -> Mapping[str, Any]:
        return await self.client.request("GET", f"/payments/{payment_id}", context, retry_class=RetryClass.SAFE_READ)

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
        return await self.client.request(
            "POST",
            f"/payments/{payment_id}/{suffix}",
            context,
            json_body=payload or None,
            idempotency_key=idempotency_key,
            retry_class=retry,
            ambiguous_command=ambiguous,
        )


class TicketRestAdapter:
    contract = (
        "openapi.ticket-service",
        "openapi/ticket-service.yaml",
        EXPECTED_FREEZE_ID,
        EXPECTED_CATALOG_SHA,
    )

    def __init__(self, client: RestClient) -> None:
        self.client = client

    async def issue_tickets(self, payload: Mapping[str, Any], idempotency_key: str, context: RequestContext) -> Sequence[Mapping[str, Any]]:
        return await self.client.request(
            "POST",
            "/tickets:issue",
            context,
            json_body=payload,
            idempotency_key=idempotency_key,
            retry_class=RetryClass.IDEMPOTENT_COMMAND,
        )

    async def list_booking_tickets(self, booking_id: str, context: RequestContext) -> Sequence[Mapping[str, Any]]:
        return await self.client.request(
            "GET",
            f"/bookings/{booking_id}/tickets",
            context,
            retry_class=RetryClass.SAFE_READ,
        )

    async def cancel_ticket(self, ticket_id: str, idempotency_key: str, context: RequestContext) -> Mapping[str, Any]:
        return await self.client.request(
            "POST",
            f"/tickets/{ticket_id}/cancel",
            context,
            idempotency_key=idempotency_key,
            retry_class=RetryClass.IDEMPOTENT_COMMAND,
        )


class NotificationRestAdapter:
    contract = (
        "openapi.notification-service",
        "openapi/notification-service.yaml",
        EXPECTED_FREEZE_ID,
        EXPECTED_CATALOG_SHA,
    )

    def __init__(self, client: RestClient, secret: str) -> None:
        self.client, self.secret = client, secret.encode()

    async def publish(self, payload: Mapping[str, Any], message_id: str, context: RequestContext) -> None:
        timestamp = str(int(datetime.now(timezone.utc).timestamp()))
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
        signature = hmac.new(self.secret, timestamp.encode() + b"." + raw, hashlib.sha256).hexdigest()
        await self.client.request(
            "POST",
            "/webhooks/events",
            context,
            raw_body=raw,
            retry_class=RetryClass.SIDE_EFFECT,
            extra_headers={
                "Content-Type": "application/json",
                "X-Webhook-Timestamp": timestamp,
                "X-Webhook-Signature": signature,
            },
        )


class RealtimeRestAdapter:
    contract = (
        "openapi.realtime-service",
        "openapi/realtime-service.yaml",
        EXPECTED_FREEZE_ID,
        EXPECTED_CATALOG_SHA,
    )

    def __init__(self, client: RestClient, service_token: str | None, caller_service: str = "booking-orchestrator") -> None:
        self.client = client
        self.service_token = service_token
        self.caller_service = caller_service

    async def publish(self, payload: Mapping[str, Any], message_id: str, context: RequestContext) -> None:
        if not self.service_token:
            raise DependencyFailure(
                "REALTIME_AUTH_CONFIGURATION_INVALID",
                "Realtime internal credential is not configured.",
                503,
                False,
            )
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
            extra_headers={
                "X-Service-Token": self.service_token,
                "X-Caller-Service": self.caller_service,
            },
        )
