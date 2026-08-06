from __future__ import annotations

from typing import Any

from app.application.evidence import booking_evidence
from app.domain.errors import Forbidden
from app.domain.models import RequestContext


def _booking_payment_status(value: object) -> str | None:
    if value is None:
        return None
    status = str(value).upper()
    mapping = {
        "PENDING": "PENDING",
        "PROCESSING": "PROCESSING",
        "AUTHORIZED": "PROCESSING",
        "CAPTURED": "SUCCEEDED",
        "SUCCEEDED": "SUCCEEDED",
        "UNKNOWN": "UNKNOWN",
        "PENDING_RECONCILIATION": "UNKNOWN",
        "FAILED": "FAILED",
        "DECLINED": "FAILED",
        "CANCELLED": "FAILED",
        "REFUND_PENDING": "REFUND_PENDING",
        "PARTIALLY_REFUNDED": "REFUND_PENDING",
        "REFUNDED": "REFUNDED",
    }
    return mapping.get(status, "UNKNOWN")


class CancellationSaga:
    """Booking decides whether cancellation is allowed; ESB executes accepted compensation."""

    def __init__(self, booking, payment, seat, ticket, customer):
        self.booking = booking
        self.payment = payment
        self.seat = seat
        self.ticket = ticket
        self.customer = customer

    async def cancel(
        self,
        booking_id: str,
        request: dict[str, Any],
        key: str,
        ctx: RequestContext,
    ) -> dict[str, Any]:
        booking = await self.booking.get(booking_id, ctx)
        customer_id = ctx.principal.customer_id
        if not customer_id:
            customer = await self.customer.resolve_identity(ctx.principal.subject, ctx)
            customer_id = str(customer.get("customerId") or customer.get("id"))
        if str(booking.get("customerId")) != str(customer_id):
            raise Forbidden("Booking does not belong to authenticated customer")

        payment_id = booking.get("paymentId")
        reservation_id = booking.get("reservationId")
        ticket_ids = booking.get("ticketIds") or []
        requires_compensation = bool(payment_id or reservation_id or ticket_ids)

        # This authoritative command is deliberately first. If Booking rejects the
        # transition, no Ticket, Payment or Seat side effect has happened.
        accepted = await self.booking.cancel(
            booking_id,
            {
                "reason": request.get("reason", "USER_REQUEST"),
                "expectedVersion": request.get(
                    "expectedVersion", booking.get("resourceVersion")
                ),
                "paymentStatus": _booking_payment_status(booking.get("paymentStatus")),
                "compensationStatus": (
                    "PENDING" if requires_compensation else "NOT_REQUIRED"
                ),
                "evidence": booking_evidence(
                    details={"requestedBy": ctx.principal.subject},
                ),
            },
            key + ":accept",
            ctx,
        )

        evidence: dict[str, Any] = {}
        complete = True
        try:
            listed = await self.ticket.list_booking(booking_id, ctx)
            rows = (
                listed.get("tickets") or listed.get("items") or []
                if isinstance(listed, dict)
                else listed
            )
            for row in rows or []:
                ticket_id = row.get("ticketId") if isinstance(row, dict) else row
                if ticket_id and str(ticket_id) not in {str(value) for value in ticket_ids}:
                    ticket_ids.append(str(ticket_id))
        except Exception as exc:
            complete = False
            evidence["ticketDiscovery"] = {
                "status": "PENDING",
                "error": str(exc),
            }

        for ticket_id in ticket_ids:
            try:
                ticket = await self.ticket.get(str(ticket_id), ctx)
                await self.ticket.cancel(
                    str(ticket_id),
                    {
                        "reason": "BOOKING_CANCELLED",
                        "expectedVersion": ticket.get("resourceVersion"),
                    },
                    key + ":ticket:" + str(ticket_id),
                    ctx,
                )
                evidence.setdefault("tickets", []).append(
                    {"ticketId": ticket_id, "status": "CANCELLED"}
                )
            except Exception as exc:
                complete = False
                evidence.setdefault("tickets", []).append(
                    {"ticketId": ticket_id, "status": "PENDING", "error": str(exc)}
                )

        if payment_id:
            try:
                payment = await self.payment.get(str(payment_id), ctx)
                status = str(payment.get("status", "")).upper()
                if status in {"CAPTURED", "PARTIALLY_REFUNDED"}:
                    # Payment Service owns refund amount validation and defaults the
                    # omitted amount to the remaining refundable balance.
                    refund = await self.payment.refund(
                        str(payment_id),
                        {
                            "reason": "BOOKING_CANCELLED",
                            "expectedVersion": payment.get("resourceVersion"),
                        },
                        key + ":refund",
                        ctx,
                    )
                    evidence["payment"] = {
                        "status": "REFUNDED",
                        "refundId": refund.get("refundId"),
                        "amountMinor": refund.get("amountMinor"),
                    }
                elif status in {"PENDING", "AUTHORIZED"}:
                    await self.payment.cancel(
                        str(payment_id),
                        {
                            "reason": "BOOKING_CANCELLED",
                            "expectedVersion": payment.get("resourceVersion"),
                        },
                        key + ":payment-cancel",
                        ctx,
                    )
                    evidence["payment"] = {"status": "CANCELLED"}
                elif status in {"REFUNDED", "CANCELLED", "FAILED"}:
                    evidence["payment"] = {"status": status, "action": "NONE"}
                else:
                    complete = False
                    evidence["payment"] = {
                        "status": status or "UNKNOWN",
                        "action": "RECONCILE",
                    }
            except Exception as exc:
                complete = False
                evidence["payment"] = {"status": "PENDING", "error": str(exc)}

        if reservation_id:
            try:
                await self.seat.release(
                    str(reservation_id),
                    "BOOKING_CANCELLED",
                    key + ":release",
                    ctx,
                )
                evidence["reservation"] = {"status": "RELEASED"}
            except Exception as exc:
                complete = False
                evidence["reservation"] = {"status": "PENDING", "error": str(exc)}

        return await self.booking.record_compensation(
            booking_id,
            {
                "compensationStatus": "COMPLETED" if complete else "PENDING",
                "expectedVersion": accepted.get("resourceVersion"),
                "reason": "BOOKING_CANCELLED",
                "evidence": booking_evidence(
                    reservation_released=(
                        evidence.get("reservation", {}).get("status") == "RELEASED"
                    ),
                    payment_refunded=(
                        evidence.get("payment", {}).get("status") == "REFUNDED"
                    ),
                    compensation_completed=complete,
                    details=evidence,
                ),
            },
            key + ":result",
            ctx,
        )
