"""Payment response contracts."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.entities import Payment
from app.domain.enums import PaymentStatus, RefundKind
from app.domain.value_objects import PaymentPage, Refund


class ResponseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class PaymentResponse(ResponseModel):
    id: str
    payment_id: str = Field(alias="paymentId")
    booking_id: str = Field(alias="bookingId")
    customer_id: str = Field(alias="customerId")
    amount: Decimal
    currency: str
    payment_method: str = Field(alias="paymentMethod")
    provider: str
    provider_reference: str | None = Field(default=None, alias="providerReference")
    status: PaymentStatus
    captured_amount: Decimal = Field(alias="capturedAmount")
    refunded_amount: Decimal = Field(alias="refundedAmount")
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

    @classmethod
    def from_entity(cls, payment: Payment) -> PaymentResponse:
        return cls(
            id=payment.payment_id,
            paymentId=payment.payment_id,
            bookingId=payment.booking_id,
            customerId=payment.customer_id,
            amount=payment.amount,
            currency=payment.currency,
            paymentMethod=payment.payment_method,
            provider=payment.provider,
            providerReference=payment.provider_reference,
            status=payment.status,
            capturedAmount=payment.captured_amount,
            refundedAmount=payment.refunded_amount,
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
            currency=refund.currency,
            reason=refund.reason,
            kind=refund.kind,
            providerReference=refund.provider_reference,
            createdAt=refund.created_at,
        )


class RefundListResponse(ResponseModel):
    items: list[RefundResponse]
