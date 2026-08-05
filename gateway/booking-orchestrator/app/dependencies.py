from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from time import monotonic
from typing import Protocol

import httpx

from app.application.booking import BookingSaga
from app.application.cancellation import CancellationSaga
from app.application.health import HealthService
from app.application.queries import QueryService
from app.domain.models import Principal
from app.persistence.database import Database
from app.ports.providers import BookingPort
from app.workers.outbox import OutboxDispatcher
from app.workers.reconciliation import ReconciliationWorker


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)

    def monotonic(self) -> float:
        return monotonic()


class BrowserAuthenticator(Protocol):
    async def verify(self, token: str) -> Principal: ...


class TicketIssuer(Protocol):
    def issue(self, subject: str, booking_id: str) -> tuple[str, datetime]: ...


@dataclass
class RuntimeContainer:
    booking_saga: BookingSaga
    cancellation_saga: CancellationSaga
    queries: QueryService
    browser_auth: BrowserAuthenticator
    ws_tickets: TicketIssuer
    bookings: BookingPort
    health: HealthService
    outbox_worker: OutboxDispatcher | None = None
    reconciliation_worker: ReconciliationWorker | None = None
    database: Database | None = None
    http_client: httpx.AsyncClient | None = None
