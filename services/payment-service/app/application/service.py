"""Payment use-case facade with bounded persistence retries."""

from collections.abc import Callable
from decimal import Decimal

from sqlalchemy.orm import Session, sessionmaker

from app.application.commands.authorize_payment import authorize_payment
from app.application.commands.cancel_payment import cancel_payment
from app.application.commands.capture_payment import capture_payment
from app.application.commands.create_payment import create_payment
from app.application.commands.reconcile_payment import reconcile_payment
from app.application.commands.refund_payment import refund_payment
from app.application.queries.get_payment import get_payment
from app.application.queries.list_payments import list_payments
from app.application.queries.list_refunds import list_refunds
from app.config import Settings
from app.domain.entities import Payment
from app.domain.enums import PaymentStatus
from app.domain.value_objects import PaymentPage, Refund, RequestContext
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
    ) -> Payment:
        return self._execute(
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
            )
        )

    def authorize(
        self,
        context: RequestContext,
        *,
        idempotency_key: str,
        payment_id: str,
        approved: bool,
        provider_reference: str | None,
        failure_code: str | None,
        reason: str | None,
        expected_version: int,
    ) -> Payment:
        return self._execute(
            lambda session: authorize_payment(
                session,
                self.settings,
                context,
                idempotency_key=idempotency_key,
                payment_id=payment_id,
                approved=approved,
                provider_reference=provider_reference,
                failure_code=failure_code,
                reason=reason,
                expected_version=expected_version,
            )
        )

    def capture(
        self,
        context: RequestContext,
        *,
        idempotency_key: str,
        payment_id: str,
        succeeded: bool,
        provider_reference: str,
        failure_code: str | None,
        reason: str | None,
        expected_version: int,
    ) -> Payment:
        return self._execute(
            lambda session: capture_payment(
                session,
                self.settings,
                context,
                idempotency_key=idempotency_key,
                payment_id=payment_id,
                succeeded=succeeded,
                provider_reference=provider_reference,
                failure_code=failure_code,
                reason=reason,
                expected_version=expected_version,
            )
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
    ) -> Payment:
        return self._execute(
            lambda session: cancel_payment(
                session,
                self.settings,
                context,
                idempotency_key=idempotency_key,
                payment_id=payment_id,
                reason=reason,
                provider_reference=provider_reference,
                expected_version=expected_version,
            )
        )

    def refund(
        self,
        context: RequestContext,
        *,
        idempotency_key: str,
        payment_id: str,
        amount: Decimal,
        reason: str,
        provider_refund_reference: str,
        expected_version: int,
    ) -> Payment:
        return self._execute(
            lambda session: refund_payment(
                session,
                self.settings,
                context,
                idempotency_key=idempotency_key,
                payment_id=payment_id,
                amount=amount,
                reason=reason,
                provider_refund_reference=provider_refund_reference,
                expected_version=expected_version,
            )
        )

    def reconcile(
        self,
        context: RequestContext,
        *,
        idempotency_key: str,
        payment_id: str,
        provider_status: PaymentStatus,
        provider_reference: str | None,
        provider_refund_reference: str | None,
        observed_refunded_amount: Decimal | None,
        failure_code: str | None,
        reason: str | None,
        expected_version: int,
    ) -> Payment:
        return self._execute(
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
            )
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

    def _execute[T](
        self,
        operation: Callable[[Session], T],
        *,
        max_retries: int = 1,
    ) -> T:
        return execute_database_operation(
            self._sessions, operation, max_retries=max_retries
        )
