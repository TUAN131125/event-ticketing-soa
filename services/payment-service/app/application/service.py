"""Application facade for all Payment Service use cases.

The facade is transport-neutral: REST handlers, workers and tests share the same
transactional commands and bounded database retry policy.
"""

from collections.abc import Callable
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session, sessionmaker

from app.application.commands.authorize_payment import authorize_payment
from app.application.commands.cancel_payment import cancel_payment
from app.application.commands.capture_payment import capture_payment
from app.application.commands.create_payment import create_payment
from app.application.commands.handle_provider_callback import handle_provider_callback
from app.application.commands.reconcile_payment import reconcile_payment
from app.application.commands.refund_payment import refund_payment
from app.application.queries.due_reconciliations import due_reconciliations
from app.application.queries.get_payment import get_payment
from app.application.queries.list_payments import list_payments
from app.application.queries.list_provider_events import query_provider_events
from app.application.queries.list_refunds import list_refunds
from app.application.queries.outbox_backlog import outbox_backlog
from app.application.queries.payment_status_counts import payment_status_counts
from app.config import Settings
from app.domain.entities import Payment
from app.domain.enums import (
    PaymentStatus,
    ProviderOperation,
    ReconciliationStatus,
)
from app.domain.exceptions import ProviderUnavailable
from app.domain.value_objects import (
    BookingPaymentEvidence,
    PaymentPage,
    ProviderEvent,
    Refund,
    RequestContext,
)
from app.observability.metrics import COMMAND_TOTAL
from app.resilience.retry import execute_database_operation


class PaymentService:
    def __init__(
        self, settings: Settings, session_factory: sessionmaker[Session]
    ) -> None:
        self.settings = settings
        self._sessions = session_factory

    @property
    def session_factory(self) -> sessionmaker[Session]:
        return self._sessions

    def create(
        self,
        context: RequestContext,
        *,
        idempotency_key: str,
        booking_id: str,
        customer_id: str,
        amount: Decimal,
        currency: str,
        payment_method: str,
        provider: str,
        method_token: str | None = None,
        booking_evidence: BookingPaymentEvidence | None = None,
    ) -> Payment:
        return self._execute_command(
            "create",
            lambda session: create_payment(
                session,
                self.settings,
                context,
                idempotency_key=idempotency_key,
                booking_id=booking_id,
                customer_id=customer_id,
                amount=amount,
                currency=currency,
                payment_method=payment_method,
                provider=provider,
                method_token=method_token,
                booking_evidence=booking_evidence,
            ),
        )

    def authorize(
        self,
        context: RequestContext,
        *,
        idempotency_key: str,
        payment_id: str,
        approved: bool | None,
        provider_reference: str | None,
        failure_code: str | None,
        reason: str | None,
        expected_version: int,
        provider_status: PaymentStatus | None = None,
    ) -> Payment:
        return self._execute_command(
            "authorize",
            lambda session: authorize_payment(
                session,
                self.settings,
                context,
                idempotency_key=idempotency_key,
                payment_id=payment_id,
                approved=approved,
                provider_status=provider_status,
                provider_reference=provider_reference,
                failure_code=failure_code,
                reason=reason,
                expected_version=expected_version,
            ),
        )

    def capture(
        self,
        context: RequestContext,
        *,
        idempotency_key: str,
        payment_id: str,
        succeeded: bool | None,
        provider_reference: str | None,
        failure_code: str | None,
        reason: str | None,
        expected_version: int,
        provider_status: PaymentStatus | None = None,
    ) -> Payment:
        return self._execute_command(
            "capture",
            lambda session: capture_payment(
                session,
                self.settings,
                context,
                idempotency_key=idempotency_key,
                payment_id=payment_id,
                succeeded=succeeded,
                provider_status=provider_status,
                provider_reference=provider_reference,
                failure_code=failure_code,
                reason=reason,
                expected_version=expected_version,
            ),
        )

    def cancel(
        self,
        context: RequestContext,
        *,
        idempotency_key: str,
        payment_id: str,
        reason: str,
        provider_reference: str | None,
        expected_version: int,
        provider_status: PaymentStatus | None = None,
    ) -> Payment:
        return self._execute_command(
            "cancel",
            lambda session: cancel_payment(
                session,
                self.settings,
                context,
                idempotency_key=idempotency_key,
                payment_id=payment_id,
                reason=reason,
                provider_reference=provider_reference,
                provider_status=provider_status,
                expected_version=expected_version,
            ),
        )

    def refund(
        self,
        context: RequestContext,
        *,
        idempotency_key: str,
        payment_id: str,
        amount: Decimal,
        reason: str,
        provider_refund_reference: str | None,
        expected_version: int,
        provider_status: PaymentStatus | None = None,
    ) -> Payment:
        return self._execute_command(
            "refund",
            lambda session: refund_payment(
                session,
                self.settings,
                context,
                idempotency_key=idempotency_key,
                payment_id=payment_id,
                amount=amount,
                reason=reason,
                provider_refund_reference=provider_refund_reference,
                provider_status=provider_status,
                expected_version=expected_version,
            ),
        )

    def reconcile(
        self,
        context: RequestContext,
        *,
        idempotency_key: str,
        payment_id: str,
        provider_status: PaymentStatus | None,
        provider_reference: str | None,
        provider_refund_reference: str | None,
        observed_refunded_amount: Decimal | None,
        failure_code: str | None,
        reason: str | None,
        expected_version: int,
    ) -> Payment:
        payment = self._execute_command(
            "reconcile",
            lambda session: reconcile_payment(
                session,
                self.settings,
                context,
                idempotency_key=idempotency_key,
                payment_id=payment_id,
                provider_status=provider_status,
                provider_reference=provider_reference,
                provider_refund_reference=provider_refund_reference,
                observed_refunded_amount=observed_refunded_amount,
                failure_code=failure_code,
                reason=reason,
                expected_version=expected_version,
            ),
        )
        # The command commits failure evidence and backoff first. Returning a 503
        # afterwards keeps the API honest without rolling that evidence back.
        if (
            provider_status is None
            and payment.status == PaymentStatus.UNKNOWN
            and payment.reconciliation_status == ReconciliationStatus.FAILED
        ):
            raise ProviderUnavailable()
        return payment

    def provider_callback(
        self,
        context: RequestContext,
        *,
        event_id: str,
        payment_id: str,
        provider: str,
        operation: ProviderOperation,
        provider_status: PaymentStatus,
        provider_reference: str | None,
        provider_refund_reference: str | None,
        amount: Decimal | None,
        currency: str | None,
        observed_refunded_amount: Decimal | None,
        failure_code: str | None,
        reason: str | None,
        occurred_at: datetime,
        payload_hash: str,
    ) -> Payment:
        return self._execute_command(
            "provider_callback",
            lambda session: handle_provider_callback(
                session,
                self.settings,
                context,
                event_id=event_id,
                payment_id=payment_id,
                provider=provider,
                operation=operation,
                provider_status=provider_status,
                provider_reference=provider_reference,
                provider_refund_reference=provider_refund_reference,
                amount=amount,
                currency=currency,
                observed_refunded_amount=observed_refunded_amount,
                failure_code=failure_code,
                reason=reason,
                occurred_at=occurred_at,
                payload_hash=payload_hash,
            ),
        )

    def get(self, payment_id: str) -> Payment:
        return self._execute(
            lambda session: get_payment(session, self.settings, payment_id)
        )

    def list(
        self,
        *,
        page: int,
        page_size: int,
        booking_id: str | None,
        customer_id: str | None,
        provider: str | None,
        status: PaymentStatus | None,
        search: str | None,
    ) -> PaymentPage:
        return self._execute(
            lambda session: list_payments(
                session,
                self.settings,
                page=page,
                page_size=page_size,
                booking_id=booking_id,
                customer_id=customer_id,
                provider=provider,
                status=status,
                search=search,
            ),
            max_retries=0,
        )

    def refunds(self, payment_id: str) -> tuple[Refund, ...]:
        return self._execute(
            lambda session: list_refunds(session, self.settings, payment_id),
            max_retries=0,
        )

    def provider_events(self, payment_id: str) -> tuple[ProviderEvent, ...]:
        return self._execute(
            lambda session: query_provider_events(
                session, self.settings, payment_id
            ),
            max_retries=0,
        )

    def due_reconciliations(
        self, *, limit: int | None = None
    ) -> tuple[tuple[str, int], ...]:
        batch_size = limit or self.settings.provider_reconciliation_batch_size
        return self._execute(
            lambda session: due_reconciliations(
                session,
                self.settings,
                limit=batch_size,
            ),
            max_retries=0,
        )

    def status_counts(self) -> dict[str, int]:
        return self._execute(
            lambda session: payment_status_counts(session, self.settings),
            max_retries=0,
        )

    def outbox_backlog(self) -> tuple[int, int]:
        return self._execute(
            lambda session: outbox_backlog(session, self.settings),
            max_retries=0,
        )

    def _execute[T](
        self,
        operation: Callable[[Session], T],
        *,
        max_retries: int = 1,
    ) -> T:
        return execute_database_operation(
            self._sessions, operation, max_retries=max_retries
        )

    def _execute_command(
        self, command: str, operation: Callable[[Session], Payment]
    ) -> Payment:
        try:
            payment = self._execute(operation)
        except Exception:
            COMMAND_TOTAL.labels(command, "failure").inc()
            raise
        COMMAND_TOTAL.labels(command, "success").inc()
        return payment
