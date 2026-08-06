"""Closed request contracts for Booking Service commands.

The models accept both the legacy service payloads and the canonical payloads
used by the current ESB contract.  Aliases are transport compatibility only;
the application layer receives one normalized command.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.domain.enums import CompensationStatus, PaymentStatus


class ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class BookingItemRequest(ClosedModel):
    seat_id: str = Field(alias="seatId", min_length=1, max_length=128)
    ticket_type: str = Field(
        validation_alias=AliasChoices("ticketType", "ticketTypeCode"),
        serialization_alias="ticketType",
        min_length=1,
        max_length=128,
    )
    unit_price: Decimal = Field(alias="unitPrice", ge=0, max_digits=18)
    price_currency: str | None = Field(
        default=None, alias="priceCurrency", min_length=3, max_length=3
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_money_object(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        price = data.get("unitPrice")
        if isinstance(price, dict):
            data["unitPrice"] = price.get("amountMinor")
            data.setdefault("priceCurrency", price.get("currency"))
        return data

    @field_validator("price_currency")
    @classmethod
    def uppercase_item_currency(cls, value: str | None) -> str | None:
        return value.upper() if value is not None else None


class CreateBookingRequest(ClosedModel):
    customer_id: str = Field(alias="customerId", min_length=1, max_length=128)
    event_id: str = Field(alias="eventId", min_length=1, max_length=128)
    reservation_id: str | None = Field(
        default=None, alias="reservationId", min_length=1, max_length=128
    )
    payment_method: str | None = Field(
        default=None, alias="paymentMethod", min_length=1, max_length=40
    )
    items: list[BookingItemRequest] = Field(min_length=1, max_length=50)
    total_amount: Decimal | None = Field(
        default=None, alias="totalAmount", ge=0, max_digits=18
    )
    currency: str | None = Field(default=None, min_length=3, max_length=3)

    @field_validator("currency")
    @classmethod
    def uppercase_currency(cls, value: str | None) -> str | None:
        return value.upper() if value is not None else None

    @model_validator(mode="after")
    def validate_currency_source(self) -> CreateBookingRequest:
        currencies = {
            item.price_currency
            for item in self.items
            if item.price_currency is not None
        }
        if len(currencies) > 1:
            raise ValueError("All item prices must use the same currency")
        item_currency = next(iter(currencies), None)
        if self.currency is None and item_currency is None:
            raise ValueError(
                "currency is required for legacy numeric unitPrice values"
            )
        if self.currency is not None and item_currency not in {None, self.currency}:
            raise ValueError("currency does not match item price currency")
        self.currency = self.currency or item_currency
        return self


class EvidenceRequest(ClosedModel):
    provider_reference: str | None = Field(
        default=None, alias="providerReference", max_length=128
    )
    reservation_expires_at: datetime | None = Field(
        default=None, alias="reservationExpiresAt"
    )
    verified_at: datetime | None = Field(default=None, alias="verifiedAt")
    reservation_released: bool = Field(default=False, alias="reservationReleased")
    payment_refunded: bool = Field(default=False, alias="paymentRefunded")
    compensation_completed: bool | None = Field(
        default=None, alias="compensationCompleted"
    )
    seat_confirmed: bool | None = Field(default=None, alias="seatConfirmed")
    tickets_issued: bool | None = Field(default=None, alias="ticketsIssued")
    payment_captured: bool | None = Field(default=None, alias="paymentCaptured")
    resolved_payment_status: PaymentStatus | None = Field(
        default=None,
        validation_alias=AliasChoices("resolvedPaymentStatus", "paymentStatus"),
        serialization_alias="resolvedPaymentStatus",
    )
    details: dict[str, Any] = Field(default_factory=dict)

    @field_validator("resolved_payment_status", mode="before")
    @classmethod
    def normalize_resolved_payment_status(cls, value: Any) -> Any:
        if value is None or isinstance(value, PaymentStatus):
            return value
        aliases = {
            "CAPTURED": PaymentStatus.SUCCEEDED,
            "PAID": PaymentStatus.SUCCEEDED,
            "SUCCEEDED": PaymentStatus.SUCCEEDED,
            "DECLINED": PaymentStatus.FAILED,
            "FAILED": PaymentStatus.FAILED,
            "UNKNOWN": PaymentStatus.UNKNOWN,
            "PENDING_RECONCILIATION": PaymentStatus.UNKNOWN,
            "REFUNDED": PaymentStatus.REFUNDED,
        }
        normalized = str(value).upper()
        if normalized not in aliases:
            raise ValueError("Unsupported resolvedPaymentStatus")
        return aliases[normalized]


class AttachReservationRequest(ClosedModel):
    reservation_id: str = Field(alias="reservationId", min_length=1, max_length=128)
    expected_version: int | None = Field(
        default=None, alias="expectedVersion", ge=1
    )
    reservation_version: int | None = Field(
        default=None, alias="reservationVersion", ge=1
    )
    reservation_expires_at: datetime | None = Field(
        default=None, alias="reservationExpiresAt"
    )
    confirmed: bool | None = None
    evidence: EvidenceRequest | None = None

    @property
    def resolved_expires_at(self) -> datetime | None:
        return self.reservation_expires_at or (
            self.evidence.reservation_expires_at if self.evidence else None
        )

    @property
    def resolved_confirmed(self) -> bool:
        if self.confirmed is not None:
            return self.confirmed
        if self.evidence is not None:
            return bool(self.evidence.seat_confirmed)
        # Compatibility with v1.1: the old endpoint represented confirmed
        # reservation evidence when no structured evidence object existed.
        return True


class ConfirmReservationRequest(ClosedModel):
    reservation_id: str = Field(alias="reservationId", min_length=1, max_length=128)
    expected_version: int | None = Field(
        default=None, alias="expectedVersion", ge=1
    )
    reservation_version: int | None = Field(
        default=None, alias="reservationVersion", ge=1
    )
    evidence: EvidenceRequest | None = None

    @model_validator(mode="after")
    def require_positive_confirmation(self) -> ConfirmReservationRequest:
        if self.evidence is not None and self.evidence.seat_confirmed is False:
            raise ValueError("seatConfirmed must be true for reservation confirmation")
        return self


class StartPaymentRequest(ClosedModel):
    payment_id: str = Field(alias="paymentId", min_length=1, max_length=128)
    expected_version: int | None = Field(
        default=None, alias="expectedVersion", ge=1
    )


class RecordPaymentRequest(ClosedModel):
    payment_id: str = Field(alias="paymentId", min_length=1, max_length=128)
    expected_version: int | None = Field(
        default=None, alias="expectedVersion", ge=1
    )
    succeeded: bool | None = None
    payment_status: str | None = Field(default=None, alias="paymentStatus")
    failure_code: str | None = Field(
        default=None, alias="failureCode", max_length=128
    )
    evidence: EvidenceRequest | None = None

    @model_validator(mode="after")
    def require_outcome(self) -> RecordPaymentRequest:
        if self.succeeded is None and self.payment_status is None:
            raise ValueError("succeeded or paymentStatus is required")
        if self.succeeded is not None and self.payment_status is not None:
            legacy = PaymentStatus.SUCCEEDED if self.succeeded else PaymentStatus.FAILED
            if self.resolved_status != legacy:
                raise ValueError("succeeded and paymentStatus disagree")
        return self

    @property
    def resolved_status(self) -> PaymentStatus:
        if self.payment_status is None:
            return PaymentStatus.SUCCEEDED if self.succeeded else PaymentStatus.FAILED
        normalized = self.payment_status.upper()
        aliases = {
            "CAPTURED": PaymentStatus.SUCCEEDED,
            "PAID": PaymentStatus.SUCCEEDED,
            "SUCCEEDED": PaymentStatus.SUCCEEDED,
            "DECLINED": PaymentStatus.FAILED,
            "FAILED": PaymentStatus.FAILED,
            "UNKNOWN": PaymentStatus.UNKNOWN,
            "PENDING_RECONCILIATION": PaymentStatus.UNKNOWN,
        }
        if normalized not in aliases:
            raise ValueError("Unsupported paymentStatus")
        return aliases[normalized]


class AttachTicketsRequest(ClosedModel):
    ticket_ids: list[str] = Field(alias="ticketIds", min_length=1, max_length=50)
    expected_version: int | None = Field(
        default=None, alias="expectedVersion", ge=1
    )
    evidence: EvidenceRequest | None = None

    @model_validator(mode="after")
    def require_issued_evidence(self) -> AttachTicketsRequest:
        if self.evidence is not None and self.evidence.tickets_issued is False:
            raise ValueError(
                "ticketsIssued must be true when ticket evidence is attached"
            )
        return self


class ConfirmBookingRequest(ClosedModel):
    expected_version: int | None = Field(
        default=None, alias="expectedVersion", ge=1
    )
    reservation_id: str | None = Field(
        default=None, alias="reservationId", max_length=128
    )
    payment_id: str | None = Field(default=None, alias="paymentId", max_length=128)
    payment_status: str | None = Field(default=None, alias="paymentStatus")
    ticket_ids: list[str] | None = Field(default=None, alias="ticketIds")
    evidence: EvidenceRequest | None = None

    @model_validator(mode="after")
    def validate_supplied_evidence(self) -> ConfirmBookingRequest:
        if (
            self.payment_status is not None
            and self.resolved_payment_status != PaymentStatus.SUCCEEDED
        ):
            raise ValueError("paymentStatus must represent a captured payment")
        if self.evidence is not None:
            checks = {
                "seatConfirmed": self.evidence.seat_confirmed,
                "paymentCaptured": self.evidence.payment_captured,
                "ticketsIssued": self.evidence.tickets_issued,
            }
            invalid = [name for name, value in checks.items() if value is False]
            if invalid:
                joined = ", ".join(invalid)
                raise ValueError(f"Confirmation evidence is false: {joined}")
        return self

    @property
    def resolved_payment_status(self) -> PaymentStatus | None:
        if self.payment_status is None:
            return None
        normalized = self.payment_status.upper()
        if normalized in {"CAPTURED", "PAID", "SUCCEEDED"}:
            return PaymentStatus.SUCCEEDED
        if normalized in {"DECLINED", "FAILED"}:
            return PaymentStatus.FAILED
        if normalized in {"UNKNOWN", "PENDING_RECONCILIATION"}:
            return PaymentStatus.UNKNOWN
        raise ValueError("Unsupported paymentStatus")


class FailBookingRequest(ClosedModel):
    failure_code: str = Field(
        validation_alias=AliasChoices("failureCode", "reasonCode"),
        serialization_alias="failureCode",
        min_length=1,
        max_length=128,
    )
    reason: str | None = Field(default=None, min_length=1, max_length=2_000)
    expected_version: int | None = Field(
        default=None, alias="expectedVersion", ge=1
    )
    compensation_status: CompensationStatus | None = Field(
        default=None, alias="compensationStatus"
    )
    evidence: EvidenceRequest | None = None

    @model_validator(mode="after")
    def default_reason_to_code(self) -> FailBookingRequest:
        self.reason = self.reason or self.failure_code
        if self.compensation_status is None and self.evidence is not None:
            if self.evidence.compensation_completed is True:
                self.compensation_status = CompensationStatus.COMPLETED
            elif self.evidence.compensation_completed is False:
                self.compensation_status = CompensationStatus.PENDING
        return self


class CancelBookingRequest(ClosedModel):
    reason: str = Field(min_length=1, max_length=2_000)
    expected_version: int | None = Field(
        default=None, alias="expectedVersion", ge=1
    )
    payment_status: PaymentStatus | None = Field(default=None, alias="paymentStatus")
    compensation_status: CompensationStatus | None = Field(
        default=None, alias="compensationStatus"
    )
    evidence: EvidenceRequest | None = None


class CompensationResultRequest(ClosedModel):
    expected_version: int | None = Field(
        default=None, alias="expectedVersion", ge=1
    )
    compensation_status: CompensationStatus = Field(alias="compensationStatus")
    reason: str | None = Field(default=None, max_length=2_000)
    evidence: EvidenceRequest
