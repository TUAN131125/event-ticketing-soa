"""In-memory test and PostgreSQL Event repositories."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.domain.entities import Event
from app.domain.enums import EventStatus
from app.domain.value_objects import Money, TicketType
from app.infrastructure.database.models import EventModel, TicketTypeModel, event_id_seq
from app.infrastructure.database.session import session_scope
from app.repositories.interfaces import EventRepository


class InMemoryEventRepository(EventRepository):
    def __init__(self) -> None:
        self._data: dict[str, Event] = {}
        self._next = 2
        now = datetime.now(UTC)
        seed = Event.create(
            "EV001",
            "Dem nhac mua he",
            "Nha hat Thanh pho",
            now + timedelta(days=30),
            now - timedelta(days=1),
            now + timedelta(days=20),
            [
                TicketType("VIP", "VIP", Money(1_500_000, "VND")),
                TicketType("STANDARD", "Standard", Money(500_000, "VND")),
            ],
        )
        seed.status = EventStatus.ON_SALE
        self._data[seed.id] = seed

    def add(self, event: Event) -> None:
        self._data[event.id] = event

    def get(self, event_id: str) -> Event | None:
        return self._data.get(event_id)

    def update(self, event: Event) -> None:
        self._data[event.id] = event

    def list_all(self) -> Iterable[Event]:
        return list(self._data.values())

    def next_id(self) -> str:
        event_id = f"EV{self._next:03d}"
        self._next += 1
        return event_id


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
            TicketType(item.code, item.name, Money(item.amount_minor, item.currency))
            for item in row.ticket_types
        ],
        resource_version=row.resource_version,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _ticket_type_models(event: Event) -> list[TicketTypeModel]:
    return [
        TicketTypeModel(
            code=item.code,
            name=item.name,
            amount_minor=item.price.amount_minor,
            currency=item.price.currency,
        )
        for item in event.ticket_types
    ]


def _model(event: Event) -> EventModel:
    return EventModel(
        id=event.id,
        name=event.name,
        venue=event.venue,
        starts_at=event.starts_at,
        sale_starts_at=event.sale_starts_at,
        sale_ends_at=event.sale_ends_at,
        status=event.status.value,
        resource_version=event.resource_version,
        created_at=event.created_at,
        updated_at=event.updated_at,
        ticket_types=_ticket_type_models(event),
    )


class PostgresEventRepository(EventRepository):
    def add(self, event: Event) -> None:
        with session_scope() as session:
            session.add(_model(event))

    def get(self, event_id: str) -> Event | None:
        with session_scope() as session:
            row = session.get(
                EventModel, event_id, options=[selectinload(EventModel.ticket_types)]
            )
            return _to_entity(row) if row is not None else None

    def update(self, event: Event) -> None:
        with session_scope() as session:
            row = session.get(
                EventModel, event.id, options=[selectinload(EventModel.ticket_types)]
            )
            if row is None:
                session.add(_model(event))
                return
            row.name = event.name
            row.venue = event.venue
            row.starts_at = event.starts_at
            row.sale_starts_at = event.sale_starts_at
            row.sale_ends_at = event.sale_ends_at
            row.status = event.status.value
            row.resource_version = event.resource_version
            row.updated_at = event.updated_at
            # Build detached child rows directly: constructing a whole EventModel here
            # would cascade a second row with the same primary key into the session.
            row.ticket_types = _ticket_type_models(event)

    def list_all(self) -> Iterable[Event]:
        with session_scope() as session:
            rows = (
                session.execute(
                    select(EventModel).options(selectinload(EventModel.ticket_types))
                )
                .scalars()
                .all()
            )
            return [_to_entity(row) for row in rows]

    def next_id(self) -> str:
        with session_scope() as session:
            value = session.execute(select(event_id_seq.next_value())).scalar_one()
            return f"EV{value:03d}"
