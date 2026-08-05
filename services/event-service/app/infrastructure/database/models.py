"""SQLAlchemy models for canonical Event resources."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Sequence, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


event_id_seq = Sequence("event_id_seq", start=1, schema="event")


class EventModel(Base):
    __tablename__ = "events"
    __table_args__ = {"schema": "event"}

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    venue: Mapped[str] = mapped_column(String, nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sale_starts_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    sale_ends_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    status: Mapped[str] = mapped_column(String, nullable=False, default="DRAFT")
    resource_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    ticket_types: Mapped[list[TicketTypeModel]] = relationship(
        "TicketTypeModel",
        back_populates="event",
        cascade="all, delete-orphan",
        order_by="TicketTypeModel.id",
    )


class TicketTypeModel(Base):
    __tablename__ = "ticket_types"
    __table_args__ = {"schema": "event"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(
        String, ForeignKey("event.events.id", ondelete="CASCADE"), nullable=False
    )
    code: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String, nullable=False)
    event: Mapped[EventModel] = relationship(back_populates="ticket_types")
