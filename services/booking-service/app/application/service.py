"""Booking use-case facade with bounded persistence retries."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session, sessionmaker

from app.application.commands.attach_reservation import attach_reservation
from app.application.commands.attach_tickets import attach_tickets
from app.application.commands.cancel_booking import cancel_booking
from app.application.commands.confirm_booking import confirm_booking
from app.application.commands.confirm_reservation import confirm_reservation
from app.application.commands.count_bookings_by_status import count_bookings_by_status
from app.application.commands.create_booking import create_booking
from app.application.commands.fail_booking import fail_booking
from app.application.commands.get_booking import get_booking
from app.application.commands.get_history import get_history
from app.application.commands.list_bookings import list_bookings
from app.application.commands.list_customer_bookings import list_customer_bookings
from app.application.commands.reconcile_bookings import reconcile_bookings
from app.application.commands.record_compensation import record_compensation
from app.application.commands.record_payment import record_payment
from app.application.commands.start_payment import start_payment
from app.config import Settings
from app.domain.entities import Booking
from app.domain.enums import BookingStatus, CompensationStatus, PaymentStatus
from app.domain.value_objects import (
    BookingHistoryEntry,
    BookingItem,
    BookingPage,
    CompensationEvidence,
    ReconciliationPage,
    RequestContext,
)
from app.observability.metrics import COMMAND_TOTAL
from app.resilience.retry import execute_database_operation

SUCCESS = "success"
FAILURE = "failure"


class BookingService:
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
        customer_id: str,
        event_id: str,
        items: tuple[BookingItem, ...],
        currency: str,
        total_amount: Decimal | None = None,
        reservation_id: str | None = None,
        payment_method: str | None = None,
    ) -> Booking:
        return self._run_command(
            "create",
            lambda session: create_booking(
                session,
                self.settings,
                context,
                idempotency_key=idempotency_key,
                customer_id=customer_id,
                event_id=event_id,
                items=items,
                currency=currency,
                total_amount=total_amount,
                reservation_id=reservation_id,
                payment_method=payment_method,
            ),
        )

    def attach_reservation(
        self,
        context: RequestContext,
        *,
        idempotency_key: str,
        booking_id: str,
        reservation_id: str,
        expected_version: int,
        expires_at: datetime | None = None,
        reservation_version: int | None = None,
        confirmed: bool = True,
    ) -> Booking:
        return self._run_command(
            "attach_reservation",
            lambda session: attach_reservation(
                session,
                self.settings,
                context,
                idempotency_key=idempotency_key,
                booking_id=booking_id,
                reservation_id=reservation_id,
                expected_version=expected_version,
                expires_at=expires_at,
                reservation_version=reservation_version,
                confirmed=confirmed,
            ),
        )

    def confirm_reservation(
        self,
        context: RequestContext,
        *,
        idempotency_key: str,
        booking_id: str,
        reservation_id: str,
        expected_version: int,
        reservation_version: int | None = None,
    ) -> Booking:
        return self._run_command(
            "confirm_reservation",
            lambda session: confirm_reservation(
                session,
                self.settings,
                context,
                idempotency_key=idempotency_key,
                booking_id=booking_id,
                reservation_id=reservation_id,
                expected_version=expected_version,
                reservation_version=reservation_version,
            ),
        )

    def start_payment(
        self,
        context: RequestContext,
        *,
        idempotency_key: str,
        booking_id: str,
        payment_id: str,
        expected_version: int,
    ) -> Booking:
        return self._run_command(
            "start_payment",
            lambda session: start_payment(
                session,
                self.settings,
                context,
                idempotency_key=idempotency_key,
                booking_id=booking_id,
                payment_id=payment_id,
                expected_version=expected_version,
            ),
        )

    def record_payment(
        self,
        context: RequestContext,
        *,
        idempotency_key: str,
        booking_id: str,
        payment_id: str,
        expected_version: int,
        payment_status: PaymentStatus | None = None,
        succeeded: bool | None = None,
        provider_reference: str | None = None,
        failure_code: str | None = None,
    ) -> Booking:
        return self._run_command(
            "record_payment",
            lambda session: record_payment(
                session,
                self.settings,
                context,
                idempotency_key=idempotency_key,
                booking_id=booking_id,
                payment_id=payment_id,
                payment_status=payment_status,
                succeeded=succeeded,
                expected_version=expected_version,
                provider_reference=provider_reference,
                failure_code=failure_code,
            ),
        )

    def attach_tickets(
        self,
        context: RequestContext,
        *,
        idempotency_key: str,
        booking_id: str,
        ticket_ids: tuple[str, ...],
        expected_version: int,
    ) -> Booking:
        return self._run_command(
            "attach_tickets",
            lambda session: attach_tickets(
                session,
                self.settings,
                context,
                idempotency_key=idempotency_key,
                booking_id=booking_id,
                ticket_ids=ticket_ids,
                expected_version=expected_version,
            ),
        )

    def confirm(
        self,
        context: RequestContext,
        *,
        idempotency_key: str,
        booking_id: str,
        expected_version: int,
        reservation_id: str | None = None,
        payment_id: str | None = None,
        payment_status: PaymentStatus | None = None,
        ticket_ids: tuple[str, ...] | None = None,
        seat_confirmed: bool | None = None,
        payment_captured: bool | None = None,
        tickets_issued: bool | None = None,
    ) -> Booking:
        return self._run_command(
            "confirm",
            lambda session: confirm_booking(
                session,
                self.settings,
                context,
                idempotency_key=idempotency_key,
                booking_id=booking_id,
                expected_version=expected_version,
                reservation_id=reservation_id,
                payment_id=payment_id,
                payment_status=payment_status,
                ticket_ids=ticket_ids,
                seat_confirmed=seat_confirmed,
                payment_captured=payment_captured,
                tickets_issued=tickets_issued,
            ),
        )

    def fail(
        self,
        context: RequestContext,
        *,
        idempotency_key: str,
        booking_id: str,
        failure_code: str,
        reason: str,
        expected_version: int,
        compensation_status: CompensationStatus | None = None,
        evidence: CompensationEvidence | None = None,
    ) -> Booking:
        return self._run_command(
            "fail",
            lambda session: fail_booking(
                session,
                self.settings,
                context,
                idempotency_key=idempotency_key,
                booking_id=booking_id,
                failure_code=failure_code,
                reason=reason,
                expected_version=expected_version,
                compensation_status=compensation_status,
                evidence=evidence,
            ),
        )

    def cancel(
        self,
        context: RequestContext,
        *,
        idempotency_key: str,
        booking_id: str,
        reason: str,
        expected_version: int,
        payment_status: PaymentStatus | None = None,
        compensation_status: CompensationStatus | None = None,
        evidence: CompensationEvidence | None = None,
    ) -> Booking:
        return self._run_command(
            "cancel",
            lambda session: cancel_booking(
                session,
                self.settings,
                context,
                idempotency_key=idempotency_key,
                booking_id=booking_id,
                reason=reason,
                expected_version=expected_version,
                payment_status=payment_status,
                compensation_status=compensation_status,
                evidence=evidence,
            ),
        )

    def record_compensation(
        self,
        context: RequestContext,
        *,
        idempotency_key: str,
        booking_id: str,
        expected_version: int,
        compensation_status: CompensationStatus,
        evidence: CompensationEvidence,
        reason: str | None = None,
    ) -> Booking:
        return self._run_command(
            "record_compensation",
            lambda session: record_compensation(
                session,
                self.settings,
                context,
                idempotency_key=idempotency_key,
                booking_id=booking_id,
                expected_version=expected_version,
                compensation_status=compensation_status,
                evidence=evidence,
                reason=reason,
            ),
        )

    def get(self, booking_id: str) -> Booking:
        return self._query(
            lambda session: get_booking(session, self.settings, booking_id)
        )

    def history(self, booking_id: str) -> tuple[BookingHistoryEntry, ...]:
        return self._query(
            lambda session: get_history(session, self.settings, booking_id)
        )

    def list(
        self,
        *,
        page: int,
        page_size: int,
        customer_id: str | None,
        event_id: str | None,
        status: BookingStatus | None,
        search: str | None,
    ) -> BookingPage:
        return self._query(
            lambda session: list_bookings(
                session,
                self.settings,
                page=page,
                page_size=page_size,
                customer_id=customer_id,
                event_id=event_id,
                status=status,
                search=search,
            )
        )

    def list_for_customer(
        self, *, customer_id: str, page: int, page_size: int
    ) -> BookingPage:
        return self._query(
            lambda session: list_customer_bookings(
                session,
                self.settings,
                customer_id=customer_id,
                page=page,
                page_size=page_size,
            )
        )

    def reconcile(
        self, *, older_than_seconds: int, page: int, page_size: int
    ) -> ReconciliationPage:
        return self._query(
            lambda session: reconcile_bookings(
                session,
                self.settings,
                older_than_seconds=older_than_seconds,
                page=page,
                page_size=page_size,
            )
        )

    def count_by_status(self) -> Sequence[tuple[str, int]]:
        return self._query(
            lambda session: count_bookings_by_status(session, self.settings)
        )

    def _run_command[T](self, command: str, operation: Callable[[Session], T]) -> T:
        try:
            result = self._execute(operation)
        except Exception:
            COMMAND_TOTAL.labels(command, FAILURE).inc()
            raise
        COMMAND_TOTAL.labels(command, SUCCESS).inc()
        return result

    def _query[T](self, operation: Callable[[Session], T]) -> T:
        return self._execute(operation, max_retries=0)

    def _execute[T](
        self, operation: Callable[[Session], T], *, max_retries: int = 1
    ) -> T:
        return execute_database_operation(
            self._sessions, operation, max_retries=max_retries
        )
