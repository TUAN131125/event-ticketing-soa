"""Payment response contracts."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.entities import Payment
from app.domain.enums import (
    MockProviderScenario,
    PaymentStatus,
    ProviderOperation,
    ProviderOutcomeSource,
    ReconciliationStatus,
    RefundKind,
)
from app.domain.rules import amount_to_minor
from app.domain.value_objects import PaymentPage, ProviderEvent, Refund


class ResponseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class PaymentResponse(ResponseModel):
    id: str
    payment_id: str = Field(alias="paymentId")
    booking_id: str = Field(alias="bookingId")
    customer_id: str = Field(alias="customerId")
    amount: Decimal
    amount_minor: int = Field(alias="amountMinor")
    currency: str
    payment_method: str = Field(alias="paymentMethod")
    provider: str
    provider_reference: str | None = Field(default=None, alias="providerReference")
    status: PaymentStatus
    captured_amount: Decimal = Field(alias="capturedAmount")
    captured_amount_minor: int = Field(alias="capturedAmountMinor")
    refunded_amount: Decimal = Field(alias="refundedAmount")
    refunded_amount_minor: int = Field(alias="refundedAmountMinor")
    failure_code: str | None = Field(default=None, alias="failureCode")
    failure_reason: str | None = Field(default=None, alias="failureReason")
    cancellation_reason: str | None = Field(default=None, alias="cancellationReason")
    resource_version: int = Field(alias="resourceVersion")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    authorized_at: datetime | None = Field(default=None, alias="authorizedAt")
    captured_at: datetime | None = Field(default=None, alias="capturedAt")
    cancelled_at: datetime | None = Field(default=None, alias="cancelledAt")
    refunded_at: datetime | None = Field(default=None, alias="refundedAt")
    booking_evidence_verified: bool = Field(alias="bookingEvidenceVerified")
    booking_evidence_version: int | None = Field(
        default=None, alias="bookingEvidenceVersion"
    )
    booking_evidence_id: str | None = Field(
        default=None, alias="bookingEvidenceId"
    )
    provider_scenario: MockProviderScenario = Field(alias="providerScenario")
    last_stable_status: PaymentStatus | None = Field(
        default=None, alias="lastStableStatus"
    )
    pending_operation: ProviderOperation | None = Field(
        default=None, alias="pendingOperation"
    )
    reconciliation_status: ReconciliationStatus = Field(
        alias="reconciliationStatus"
    )
    reconciliation_attempts: int = Field(alias="reconciliationAttempts")
    unknown_since: datetime | None = Field(default=None, alias="unknownSince")
    reconciliation_due_at: datetime | None = Field(
        default=None, alias="reconciliationDueAt"
    )
    last_reconciled_at: datetime | None = Field(
        default=None, alias="lastReconciledAt"
    )
    reconciliation_error: str | None = Field(
        default=None, alias="reconciliationError"
    )

    @classmethod
    def from_entity(cls, payment: Payment) -> PaymentResponse:
        return cls(
            id=payment.payment_id,
            paymentId=payment.payment_id,
            bookingId=payment.booking_id,
            customerId=payment.customer_id,
            amount=payment.amount,
            amountMinor=amount_to_minor(payment.amount, payment.currency),
            currency=payment.currency,
            paymentMethod=payment.payment_method,
            provider=payment.provider,
            providerReference=payment.provider_reference,
            status=payment.status,
            capturedAmount=payment.captured_amount,
            capturedAmountMinor=(
                0
                if payment.captured_amount == 0
                else amount_to_minor(payment.captured_amount, payment.currency)
            ),
            refundedAmount=payment.refunded_amount,
            refundedAmountMinor=(
                0
                if payment.refunded_amount == 0
                else amount_to_minor(payment.refunded_amount, payment.currency)
            ),
            failureCode=payment.failure_code,
            failureReason=payment.failure_reason,
            cancellationReason=payment.cancellation_reason,
            resourceVersion=payment.resource_version,
            createdAt=payment.created_at,
            updatedAt=payment.updated_at,
            authorizedAt=payment.authorized_at,
            capturedAt=payment.captured_at,
            cancelledAt=payment.cancelled_at,
            refundedAt=payment.refunded_at,
            bookingEvidenceVerified=payment.booking_evidence_verified,
            bookingEvidenceVersion=payment.booking_evidence_version,
            bookingEvidenceId=payment.booking_evidence_id,
            providerScenario=payment.provider_scenario,
            lastStableStatus=payment.last_stable_status,
            pendingOperation=payment.pending_operation,
            reconciliationStatus=payment.reconciliation_status,
            reconciliationAttempts=payment.reconciliation_attempts,
            unknownSince=payment.unknown_since,
            reconciliationDueAt=payment.reconciliation_due_at,
            lastReconciledAt=payment.last_reconciled_at,
            reconciliationError=payment.reconciliation_error,
        )


class PaymentPageResponse(ResponseModel):
    items: list[PaymentResponse]
    page: int
    page_size: int = Field(alias="pageSize")
    total: int
    total_pages: int = Field(alias="totalPages")

    @classmethod
    def from_page(cls, result: PaymentPage) -> PaymentPageResponse:
        return cls(
            items=[PaymentResponse.from_entity(item) for item in result.items],
            page=result.page,
            pageSize=result.page_size,
            total=result.total,
            totalPages=result.total_pages,
        )


class RefundResponse(ResponseModel):
    refund_id: str = Field(alias="refundId")
    payment_id: str = Field(alias="paymentId")
    amount: Decimal
    amount_minor: int = Field(alias="amountMinor")
    currency: str
    reason: str
    kind: RefundKind
    provider_reference: str = Field(alias="providerReference")
    created_at: datetime = Field(alias="createdAt")

    @classmethod
    def from_value(cls, refund: Refund) -> RefundResponse:
        return cls(
            refundId=refund.refund_id,
            paymentId=refund.payment_id,
            amount=refund.amount,
            amountMinor=amount_to_minor(refund.amount, refund.currency),
            currency=refund.currency,
            reason=refund.reason,
            kind=refund.kind,
            providerReference=refund.provider_reference,
            createdAt=refund.created_at,
        )


class RefundListResponse(ResponseModel):
    items: list[RefundResponse]


class ProviderEventResponse(ResponseModel):
    event_id: str = Field(alias="eventId")
    payment_id: str = Field(alias="paymentId")
    provider: str
    operation: ProviderOperation
    provider_status: PaymentStatus = Field(alias="providerStatus")
    source: ProviderOutcomeSource
    provider_reference: str | None = Field(default=None, alias="providerReference")
    provider_refund_reference: str | None = Field(
        default=None, alias="providerRefundReference"
    )
    amount: Decimal | None = None
    currency: str | None = None
    observed_refunded_amount: Decimal | None = Field(
        default=None, alias="observedRefundedAmount"
    )
    failure_code: str | None = Field(default=None, alias="failureCode")
    reason: str | None = None
    occurred_at: datetime = Field(alias="occurredAt")
    received_at: datetime = Field(alias="receivedAt")

    @classmethod
    def from_value(cls, event: ProviderEvent) -> ProviderEventResponse:
        return cls(
            eventId=event.event_id,
            paymentId=event.payment_id,
            provider=event.provider,
            operation=event.operation,
            providerStatus=event.status,
            source=event.source,
            providerReference=event.provider_reference,
            providerRefundReference=event.provider_refund_reference,
            amount=event.amount,
            currency=event.currency,
            observedRefundedAmount=event.refunded_amount,
            failureCode=event.failure_code,
            reason=event.reason,
            occurredAt=event.occurred_at,
            receivedAt=event.received_at,
        )


class ProviderEventListResponse(ResponseModel):
    items: list[ProviderEventResponse]
