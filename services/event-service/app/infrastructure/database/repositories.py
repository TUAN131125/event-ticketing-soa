"""Cac implementation THAT cua EventRepository.

- InMemoryEventRepository: dung dict trong bo nho, chi con dung cho unit
  test (nhanh, khong can Postgres chay san). KHONG con duoc dung trong
  app that (xem dependencies.py).
- PostgresEventRepository: doc/ghi that qua SQLAlchemy + models.py, moi
  phuong thuc tu mo/dong 1 session (session_scope) nen an toan khi
  FastAPI goi dong thoi nhieu request cung luc (moi request 1 session
  rieng, khong chia se ket noi). ticket_types la bang con, duoc ghi/doc
  cung luc voi events qua relationship (khong co use case nao sua doi
  ticket_types sau khi tao, nen update() chi dong cham toi cot cua
  events, khong dung lai/tao lai ticket_types).
"""
from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.domain.entities import Event
from app.domain.enums import EventStatus
from app.domain.value_objects import TicketType
from app.infrastructure.database.models import EventModel, TicketTypeModel, event_id_seq
from app.infrastructure.database.session import session_scope
from app.repositories.interfaces import EventRepository


class InMemoryEventRepository(EventRepository):
    """Chi dung trong tests/unit - khong dung trong app that nua."""

    def __init__(self) -> None:
        self._data: dict[str, Event] = {}
        self._next = 1
        seed = Event.create(
            "EV001", "Dem nhac mua he", "Nha hat Thanh pho", "2026-08-20T19:30:00",
            [TicketType("VIP", 1500000), TicketType("STANDARD", 500000)],
        )
        seed.status = EventStatus.ON_SALE
        self._data[seed.id] = seed
        self._next = 2

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
        location=row.location,
        start_time=row.start_time,
        status=EventStatus(row.status),
        ticket_types=[TicketType(t.type, t.price) for t in row.ticket_types],
        created_at=row.created_at,
    )


class PostgresEventRepository(EventRepository):
    """Repository that, ket noi PostgreSQL qua SQLAlchemy Core/ORM."""

    def add(self, event: Event) -> None:
        with session_scope() as session:
            session.add(
                EventModel(
                    id=event.id,
                    name=event.name,
                    location=event.location,
                    start_time=event.start_time,
                    status=event.status.value,
                    created_at=event.created_at,
                    ticket_types=[
                        TicketTypeModel(type=t.type, price=t.price)
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

    def update(self, event: Event) -> None:
        with session_scope() as session:
            row = session.get(
                EventModel, event.id, options=[selectinload(EventModel.ticket_types)]
            )
            if row is None:
                # Phong thu: neu vi ly do nao do ban ghi khong con ton tai,
                # coi nhu upsert de khong lam mat du lieu da xac thuc o
                # tang domain.
                session.add(
                    EventModel(
                        id=event.id,
                        name=event.name,
                        location=event.location,
                        start_time=event.start_time,
                        status=event.status.value,
                        created_at=event.created_at,
                        ticket_types=[
                            TicketTypeModel(type=t.type, price=t.price)
                            for t in event.ticket_types
                        ],
                    )
                )
                return
            row.name = event.name
            row.location = event.location
            row.start_time = event.start_time
            row.status = event.status.value
            # Khong co use case nao sua doi ticket_types sau khi tao (xem
            # application/commands/*) nen khong dong toi row.ticket_types
            # o day - tranh xoa/tao lai khong can thiet.

    def list_all(self) -> Iterable[Event]:
        with session_scope() as session:
            stmt = select(EventModel).options(selectinload(EventModel.ticket_types))
            rows = session.execute(stmt).scalars().all()
            return [_to_entity(row) for row in rows]

    def next_id(self) -> str:
        # Dung PostgreSQL SEQUENCE de sinh so thu tu duy nhat ngay tai
        # tang database - an toan khi nhieu worker/container cung goi
        # dong thoi (khac voi bien dem trong bo nho cua ban InMemory).
        with session_scope() as session:
            next_value = session.execute(select(event_id_seq.next_value())).scalar_one()
            return f"EV{next_value:03d}"
