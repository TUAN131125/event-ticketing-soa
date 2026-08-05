"""Booking use-case facade with bounded persistence retries."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from app.application.commands.create_booking import create_booking
from app.application.commands.get_booking import get_booking
from app.application.commands.list_bookings import list_bookings
from app.application.commands.transition_booking import transition_booking
from app.config import Settings
from app.domain.entities import Booking
from app.domain.enums import BookingStatus
from app.domain.value_objects import BookingItem, BookingPage, RequestContext
from app.resilience.retry import execute_database_operation


class BookingService:
    def __init__(
        self, settings: Settings, session_factory: sessionmaker[Session]
    ) -> None:
        self.settings = settings
        self._sessions = session_factory

    @property
    def session_factory(self) -> sessionmaker[Session]:
        """Expose the managed factory for infrastructure-only read operations."""
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
    ) -> Booking:
        return self._execute(
            lambda session: create_booking(
                session,
                self.settings,
                context,
                idempotency_key=idempotency_key,
                customer_id=customer_id,
                event_id=event_id,
                items=items,
                currency=currency,
            )
        )

    def transition(
        self,
        context: RequestContext,
        *,
        operation: str,
        idempotency_key: str,
        booking_id: str,
        payload: dict[str, Any],
        expected_version: int,
    ) -> Booking:
        return self._execute(
            lambda session: transition_booking(
                session,
                self.settings,
                context,
                operation=operation,
                idempotency_key=idempotency_key,
                booking_id=booking_id,
                payload=payload,
                expected_version=expected_version,
            )
        )

    def get(self, booking_id: str) -> Booking:
        return self._execute(
            lambda session: get_booking(session, self.settings, booking_id)
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
        return self._execute(
            lambda session: list_bookings(
                session,
                self.settings,
                page=page,
                page_size=page_size,
                customer_id=customer_id,
                event_id=event_id,
                status=status,
                search=search,
            ),
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
