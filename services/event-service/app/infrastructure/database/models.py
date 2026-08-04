"""SQLAlchemy ORM model - khop voi bang duoc tao trong
migrations/versions/. events/ticket_types/event_audit/idempotency_keys
deu nam trong schema "event" (moi service tu quan ly schema cua minh)."""

from __future__ import annotations

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Sequence,
    String,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

event_id_seq = Sequence("event_id_seq", start=1, schema="event")


class EventModel(Base):
    __tablename__ = "events"
    __table_args__ = {"schema": "event"}

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    venue = Column(String, nullable=False)
    starts_at = Column(DateTime(timezone=True), nullable=False)
    sale_starts_at = Column(DateTime(timezone=True), nullable=False)
    sale_ends_at = Column(DateTime(timezone=True), nullable=False)
    status = Column(String, nullable=False, default="DRAFT")
    resource_version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), nullable=False)

    ticket_types = relationship(
        "TicketTypeModel",
        back_populates="event",
        cascade="all, delete-orphan",
        order_by="TicketTypeModel.id",
    )


class TicketTypeModel(Base):
    __tablename__ = "ticket_types"
    __table_args__ = {"schema": "event"}

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(
        String, ForeignKey("event.events.id", ondelete="CASCADE"), nullable=False
    )
    code = Column(String, nullable=False)
    name = Column(String, nullable=False)
    amount_minor = Column(Integer, nullable=False)
    currency = Column(String(3), nullable=False, default="VND")

    event = relationship("EventModel", back_populates="ticket_types")


class EventAuditModel(Base):
    """EVT-11 - bat bien, chi them (append-only), khong sua/xoa."""

    __tablename__ = "event_audit"
    __table_args__ = {"schema": "event"}

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String, nullable=False, index=True)
    actor_id = Column(String, nullable=False)
    action = Column(String, nullable=False)
    changed_at = Column(DateTime(timezone=True), nullable=False)


class IdempotencyKeyModel(Base):
    """Luu ket qua request theo scope = "{operation}:{eventId-hoac-new}:
    {Idempotency-Key}" - xem repositories.py."""

    __tablename__ = "idempotency_keys"
    __table_args__ = {"schema": "event"}

    scope = Column(String, primary_key=True)
    request_hash = Column(String, nullable=False)
    status_code = Column(Integer, nullable=False)
    response_body = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
