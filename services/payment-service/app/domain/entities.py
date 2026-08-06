"""Persistence-independent Payment aggregate and financial state machine."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from app.domain.enums import (
    MockProviderScenario,
    PaymentStatus,
    ProviderOperation,
    ReconciliationStatus,
    RefundKind,
)
from app.domain.exceptions import (
    InvalidRequest,
    ProviderReferenceConflict,
    VersionConflict,
)
from app.domain.rules import (
    ensure_transition_allowed,
    validate_identifier,
    validate_money,
    validate_optional_identifier,
    validate_reason,
)
from app.domain.value_objects import PaymentDraft, Refund


@dataclass(slots=True)
class Payment:
    payment_id: str
    booking_id: str
    customer_id: str
    amount: Decimal
    currency: str
    payment_method: str
    provider: str
    status: PaymentStatus
    captured_amount: Decimal
    refunded_amount: Decimal
    resource_version: int
    created_at: datetime
    updated_at: datetime
    provider_reference: str | None = None
    failure_code: str | None = None
    failure_reason: str | None = None
    cancellation_reason: str | None = None
    authorized_at: datetime | None = None
    captured_at: datetime | None = None
    cancelled_at: datetime | None = None
    refunded_at: datetime | None = None
    method_fingerprint: str | None = None
    provider_scenario: MockProviderScenario = MockProviderScenario.MANUAL
    booking_evidence_version: int | None = None
    booking_evidence_id: str | None = None
    booking_evidence_verified: bool = False
    last_stable_status: PaymentStatus | None = None
    pending_operation: ProviderOperation | None = None
    reconciliation_status: ReconciliationStatus = ReconciliationStatus.NOT_REQUIRED
    reconciliation_attempts: int = 0
    unknown_since: datetime | None = None
    reconciliation_due_at: datetime | None = None
    last_reconciled_at: datetime | None = None
    reconciliation_error: str | None = None

    @classmethod
    def create(
        cls,
        *,
        payment_id: str,
        draft: PaymentDraft,
        now: datetime,
    ) -> Payment:
        return cls(
            payment_id=validate_identifier(payment_id, "paymentId"),
            booking_id=draft.booking_id,
            customer_id=draft.customer_id,
            amount=draft.amount,
            currency=draft.currency,
            payment_method=draft.payment_method,
            provider=draft.provider,
            status=PaymentStatus.PENDING,
            captured_amount=Decimal("0.00"),
            refunded_amount=Decimal("0.00"),
            resource_version=1,
            created_at=now,
            updated_at=now,
            method_fingerprint=draft.method_fingerprint,
            provider_scenario=draft.provider_scenario,
            booking_evidence_version=draft.booking_evidence_version,
            booking_evidence_id=draft.booking_evidence_id,
            booking_evidence_verified=draft.booking_evidence_verified,
        )

    def definition(self) -> PaymentDraft:
        return PaymentDraft(
            booking_id=self.booking_id,
            customer_id=self.customer_id,
            amount=self.amount,
            currency=self.currency,
            payment_method=self.payment_method,
            provider=self.provider,
            method_fingerprint=self.method_fingerprint,
            provider_scenario=self.provider_scenario,
            booking_evidence_version=self.booking_evidence_version,
            booking_evidence_id=self.booking_evidence_id,
            booking_evidence_verified=self.booking_evidence_verified,
        )

    def check_version(self, expected_version: int) -> None:
        if self.resource_version != expected_version:
            raise VersionConflict(expected_version, self.resource_version)

    def authorize(
        self,
        *,
        provider_reference: str,
        expected_version: int,
        now: datetime,
        reconciled: bool = False,
    ) -> None:
        current = self._prepare_resolution(
            expected_version=expected_version,
            operation=ProviderOperation.AUTHORIZE,
            reconciled=reconciled,
        )
        ensure_transition_allowed(current, PaymentStatus.AUTHORIZED)
        self._set_provider_reference(provider_reference)
        self.status = PaymentStatus.AUTHORIZED
        self.authorized_at = self.authorized_at or now
        self._complete_outcome(now, reconciled=reconciled)

    def capture(
        self,
        *,
        provider_reference: str,
        expected_version: int,
        now: datetime,
        allow_direct: bool = False,
        reconciled: bool = False,
    ) -> None:
        current = self._prepare_resolution(
            expected_version=expected_version,
            operation=ProviderOperation.CAPTURE,
            reconciled=reconciled,
        )
        if current == PaymentStatus.PENDING and not allow_direct:
            raise InvalidRequest("Payment must be authorized before capture")
        ensure_transition_allowed(current, PaymentStatus.CAPTURED)
        self._set_provider_reference(provider_reference)
        self.status = PaymentStatus.CAPTURED
        self.captured_amount = self.amount
        self.captured_at = self.captured_at or now
        self._complete_outcome(now, reconciled=reconciled)

    def fail(
        self,
        *,
        failure_code: str,
        reason: str,
        provider_reference: str | None,
        expected_version: int,
        now: datetime,
        operation: ProviderOperation | None = None,
        reconciled: bool = False,
    ) -> None:
        current = self._prepare_resolution(
            expected_version=expected_version,
            operation=operation or self.pending_operation,
            reconciled=reconciled,
        )
        ensure_transition_allowed(current, PaymentStatus.FAILED)
        if provider_reference is not None:
            self._set_provider_reference(provider_reference)
        self.failure_code = validate_identifier(failure_code, "failureCode")
        self.failure_reason = validate_reason(reason)
        self.status = PaymentStatus.FAILED
        self._complete_outcome(now, reconciled=reconciled)

    def cancel(
        self,
        *,
        reason: str,
        provider_reference: str | None,
        expected_version: int,
        now: datetime,
        reconciled: bool = False,
    ) -> None:
        current = self._prepare_resolution(
            expected_version=expected_version,
            operation=ProviderOperation.CANCEL,
            reconciled=reconciled,
        )
        ensure_transition_allowed(current, PaymentStatus.CANCELLED)
        if provider_reference is not None:
            self._set_provider_reference(provider_reference)
        self.cancellation_reason = validate_reason(reason)
        self.status = PaymentStatus.CANCELLED
        self.cancelled_at = self.cancelled_at or now
        self._complete_outcome(now, reconciled=reconciled)

    def mark_unknown(
        self,
        *,
        operation: ProviderOperation,
        reason: str,
        expected_version: int,
        now: datetime,
        provider_reference: str | None = None,
    ) -> None:
        self.check_version(expected_version)
        if self.status == PaymentStatus.UNKNOWN:
            if self.pending_operation != operation:
                raise InvalidRequest(
                    "Payment is already awaiting another provider operation"
                )
            return
        if self.status in {
            PaymentStatus.FAILED,
            PaymentStatus.CANCELLED,
            PaymentStatus.REFUNDED,
        }:
            raise InvalidRequest("A terminal payment cannot become UNKNOWN")
        ensure_transition_allowed(self.status, PaymentStatus.UNKNOWN)
        if provider_reference is not None:
            self._set_provider_reference(provider_reference)
        self.last_stable_status = self.status
        self.status = PaymentStatus.UNKNOWN
        self.pending_operation = operation
        self.reconciliation_status = ReconciliationStatus.PENDING
        self.unknown_since = now
        self.reconciliation_due_at = now
        self.reconciliation_error = validate_reason(reason, "unknownReason")
        self._advance(now)

    def record_reconciliation_failure(
        self,
        *,
        reason: str,
        expected_version: int,
        now: datetime,
        next_due_at: datetime | None,
    ) -> None:
        self.check_version(expected_version)
        if self.status != PaymentStatus.UNKNOWN:
            raise InvalidRequest("Only an UNKNOWN payment can remain unreconciled")
        if next_due_at is not None and next_due_at < now:
            raise InvalidRequest("next reconciliation time cannot be in the past")
        self.reconciliation_status = ReconciliationStatus.FAILED
        self.reconciliation_attempts += 1
        self.last_reconciled_at = now
        self.reconciliation_due_at = next_due_at
        self.reconciliation_error = validate_reason(reason, "reconciliationError")
        self._advance(now)

    def refund(
        self,
        *,
        refund_id: str,
        amount: Decimal,
        reason: str,
        provider_reference: str,
        kind: RefundKind,
        expected_version: int,
        now: datetime,
        reconciled: bool = False,
    ) -> Refund:
        current = self._prepare_resolution(
            expected_version=expected_version,
            operation=ProviderOperation.REFUND,
            reconciled=reconciled,
        )
        if current not in {
            PaymentStatus.CAPTURED,
            PaymentStatus.PARTIALLY_REFUNDED,
        }:
            ensure_transition_allowed(current, PaymentStatus.REFUNDED)
        refund_amount = validate_money(amount, "refundAmount")
        remaining = self.captured_amount - self.refunded_amount
        if refund_amount > remaining:
            raise InvalidRequest(
                "refundAmount cannot exceed the unrefunded captured amount",
                details={
                    "refundAmount": str(refund_amount),
                    "availableAmount": str(remaining),
                },
            )
        target = (
            PaymentStatus.REFUNDED
            if refund_amount == remaining
            else PaymentStatus.PARTIALLY_REFUNDED
        )
        ensure_transition_allowed(current, target)
        normalized_reference = validate_identifier(
            provider_reference, "providerRefundReference"
        )
        normalized_reason = validate_reason(reason)
        self.refunded_amount += refund_amount
        self.status = target
        if target == PaymentStatus.REFUNDED:
            self.refunded_at = self.refunded_at or now
        self._complete_outcome(now, reconciled=reconciled)
        return Refund(
            refund_id=validate_identifier(refund_id, "refundId"),
            payment_id=self.payment_id,
            amount=refund_amount,
            currency=self.currency,
            reason=normalized_reason,
            kind=kind,
            provider_reference=normalized_reference,
            created_at=now,
        )

    def _prepare_resolution(
        self,
        *,
        expected_version: int,
        operation: ProviderOperation | None,
        reconciled: bool,
    ) -> PaymentStatus:
        self.check_version(expected_version)
        if self.status != PaymentStatus.UNKNOWN:
            return self.status
        if not reconciled:
            raise InvalidRequest(
                "UNKNOWN payment must be resolved through callback or reconciliation"
            )
        if operation is not None and self.pending_operation not in {None, operation}:
            raise InvalidRequest(
                "Provider outcome does not match the pending payment operation"
            )
        if self.last_stable_status is None:
            raise InvalidRequest("UNKNOWN payment does not contain a stable state")
        return self.last_stable_status

    def _complete_outcome(self, now: datetime, *, reconciled: bool) -> None:
        if reconciled or self.pending_operation is not None:
            self.reconciliation_status = ReconciliationStatus.COMPLETED
            self.reconciliation_attempts += 1
            self.last_reconciled_at = now
        else:
            self.reconciliation_status = ReconciliationStatus.NOT_REQUIRED
        self.last_stable_status = None
        self.pending_operation = None
        self.unknown_since = None
        self.reconciliation_due_at = None
        self.reconciliation_error = None
        self._advance(now)

    def _set_provider_reference(self, value: str) -> None:
        normalized = validate_identifier(value, "providerReference")
        if (
            self.provider_reference is not None
            and self.provider_reference != normalized
        ):
            raise ProviderReferenceConflict()
        self.provider_reference = normalized

    def provider_reference_matches(self, value: str | None) -> bool:
        normalized = validate_optional_identifier(value, "providerReference")
        return self.provider_reference == normalized

    def _advance(self, now: datetime) -> None:
        self.resource_version += 1
        self.updated_at = now
