"""Cac implementation THAT cua EventRepository/IdempotencyRepository/
AuditRepository.

- Ban InMemory*: chi con dung cho unit test (nhanh, khong can Postgres).
- Ban Postgres*: doc/ghi that qua SQLAlchemy, moi phuong thuc tu mo/dong
  1 session (session_scope) nen an toan khi FastAPI xu ly nhieu request
  dong thoi.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.domain.entities import Event
from app.domain.enums import EventStatus
from app.domain.exceptions import VersionConflictError
from app.domain.value_objects import Money, TicketType
from app.infrastructure.database.models import (
    EventAuditModel,
    EventModel,
    IdempotencyKeyModel,
    TicketTypeModel,
    event_id_seq,
)
from app.infrastructure.database.session import session_scope
from app.repositories.interfaces import (
    AuditRepository,
    EventRepository,
    IdempotencyRepository,
)


class InMemoryEventRepository(EventRepository):
    """Chi dung trong tests/unit - khong dung trong app that."""

    def __init__(self) -> None:
        self._data: dict[str, Event] = {}
        self._next = 1
        seed = Event.create(
            "EV001",
            "Dem nhac mua he",
            "Nha hat Thanh pho",
            starts_at=datetime(2026, 8, 20, 19, 30, tzinfo=UTC),
            sale_starts_at=datetime(2026, 7, 1, tzinfo=UTC),
            sale_ends_at=datetime(2026, 8, 20, 18, 0, tzinfo=UTC),
            ticket_types=[
                TicketType("VIP", "Ve VIP", Money(1500000, "VND")),
                TicketType("STANDARD", "Ve Standard", Money(500000, "VND")),
            ],
        )
        seed.status = EventStatus.ON_SALE
        self._data[seed.id] = seed
        self._next = 2

    def add(self, event: Event) -> None:
        self._data[event.id] = event

    def get(self, event_id: str) -> Event | None:
        return self._data.get(event_id)

    def update(self, event: Event, expected_version: int) -> Event:
        current = self._data.get(event.id)
        if current is not None and current.resource_version != expected_version:
            raise VersionConflictError(expected_version, current.resource_version)
        event.resource_version = expected_version + 1
        self._data[event.id] = event
        return event

    def list(
        self, status: EventStatus | None, page: int, page_size: int
    ) -> tuple[list[Event], int]:
        items = [e for e in self._data.values() if status is None or e.status == status]
        total = len(items)
        start = (page - 1) * page_size
        return items[start : start + page_size], total

    def next_id(self) -> str:
        event_id = f"EV{self._next:03d}"
        self._next += 1
        return event_id


class InMemoryIdempotencyRepository(IdempotencyRepository):
    def __init__(self) -> None:
        self._data: dict[str, tuple[str, int, dict]] = {}

    def get(self, scope: str) -> tuple[str, int, dict] | None:
        return self._data.get(scope)

    def save(
        self, scope: str, request_hash: str, status_code: int, response_body: dict
    ) -> None:
        self._data[scope] = (request_hash, status_code, response_body)


class InMemoryAuditRepository(AuditRepository):
    def __init__(self) -> None:
        self._records: list[dict] = []

    def record(self, event_id: str, actor_id: str, action: str) -> None:
        self._records.append(
            {
                "eventId": event_id,
                "actorId": actor_id,
                "action": action,
                "changedAt": datetime.now(UTC).isoformat(),
            }
        )

    def list_for_event(self, event_id: str) -> Iterable[dict]:
        return [r for r in self._records if r["eventId"] == event_id]


def _to_entity(row: EventModel) -> Event:
    return Event(
        id=row.id,
        name=row.name,
        venue=row.venue,
        starts_at=row.starts_at,
        sale_starts_at=row.sale_starts_at,
        sale_ends_at=row.sale_ends_at,
        status=EventStatus(row.status),
        ticket_types=[
            TicketType(t.code, t.name, Money(t.amount_minor, t.currency))
            for t in row.ticket_types
        ],
        resource_version=row.resource_version,
        created_at=row.created_at,
    )


class PostgresEventRepository(EventRepository):
    def add(self, event: Event) -> None:
        with session_scope() as session:
            session.add(
                EventModel(
                    id=event.id,
                    name=event.name,
                    venue=event.venue,
                    starts_at=event.starts_at,
                    sale_starts_at=event.sale_starts_at,
                    sale_ends_at=event.sale_ends_at,
                    status=event.status.value,
                    resource_version=event.resource_version,
                    created_at=event.created_at,
                    ticket_types=[
                        TicketTypeModel(
                            code=t.code,
                            name=t.name,
                            amount_minor=t.price.amount_minor,
                            currency=t.price.currency,
                        )
                        for t in event.ticket_types
                    ],
                )
            )

    def get(self, event_id: str) -> Event | None:
        with session_scope() as session:
            row = session.get(
                EventModel, event_id, options=[selectinload(EventModel.ticket_types)]
            )
            return _to_entity(row) if row is not None else None

    def update(self, event: Event, expected_version: int) -> Event:
        with session_scope() as session:
            row = session.get(
                EventModel, event.id, options=[selectinload(EventModel.ticket_types)]
            )
            if row is None:
                raise VersionConflictError(expected_version, 0)
            if row.resource_version != expected_version:
                # Doc lai gia tri that trong DB de bao loi chinh xac (co
                # the da bi admin khac ghi de sau khi client doc lan dau).
                raise VersionConflictError(expected_version, row.resource_version)

            row.name = event.name
            row.venue = event.venue
            row.starts_at = event.starts_at
            row.sale_starts_at = event.sale_starts_at
            row.sale_ends_at = event.sale_ends_at
            row.status = event.status.value
            row.resource_version = expected_version + 1

            # Ticket types la bang con, chi PUT (replace toan bo profile)
            # moi thay doi chung - xoa het roi tao lai theo danh sach moi.
            row.ticket_types = [
                TicketTypeModel(
                    code=t.code,
                    name=t.name,
                    amount_minor=t.price.amount_minor,
                    currency=t.price.currency,
                )
                for t in event.ticket_types
            ]
            session.flush()
            event.resource_version = row.resource_version
            return event

    def list(
        self, status: EventStatus | None, page: int, page_size: int
    ) -> tuple[list[Event], int]:
        with session_scope() as session:
            stmt = select(EventModel).options(selectinload(EventModel.ticket_types))
            count_stmt = select(func.count()).select_from(EventModel)
            if status is not None:
                stmt = stmt.where(EventModel.status == status.value)
                count_stmt = count_stmt.where(EventModel.status == status.value)
            total = session.execute(count_stmt).scalar_one()
            stmt = (
                stmt.order_by(EventModel.id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            rows = session.execute(stmt).scalars().all()
            return [_to_entity(row) for row in rows], total

    def next_id(self) -> str:
        with session_scope() as session:
            next_value = session.execute(select(event_id_seq.next_value())).scalar_one()
            return f"EV{next_value:03d}"


class PostgresIdempotencyRepository(IdempotencyRepository):
    def get(self, scope: str) -> tuple[str, int, dict] | None:
        with session_scope() as session:
            row = session.get(IdempotencyKeyModel, scope)
            if row is None:
                return None
            return row.request_hash, row.status_code, row.response_body

    def save(
        self, scope: str, request_hash: str, status_code: int, response_body: dict
    ) -> None:
        with session_scope() as session:
            existing = session.get(IdempotencyKeyModel, scope)
            if existing is not None:
                return  # da co ai luu truoc trong luc dua (hiem), giu ban dau.
            session.add(
                IdempotencyKeyModel(
                    scope=scope,
                    request_hash=request_hash,
                    status_code=status_code,
                    response_body=response_body,
                    created_at=datetime.now(UTC),
                )
            )


class PostgresAuditRepository(AuditRepository):
    def record(self, event_id: str, actor_id: str, action: str) -> None:
        with session_scope() as session:
            session.add(
                EventAuditModel(
                    event_id=event_id,
                    actor_id=actor_id,
                    action=action,
                    changed_at=datetime.now(UTC),
                )
            )

    def list_for_event(self, event_id: str) -> Iterable[dict]:
        with session_scope() as session:
            stmt = (
                select(EventAuditModel)
                .where(EventAuditModel.event_id == event_id)
                .order_by(EventAuditModel.id)
            )
            rows = session.execute(stmt).scalars().all()
            return [
                {
                    "eventId": r.event_id,
                    "actorId": r.actor_id,
                    "action": r.action,
                    "changedAt": r.changed_at.isoformat(),
                }
                for r in rows
            ]
