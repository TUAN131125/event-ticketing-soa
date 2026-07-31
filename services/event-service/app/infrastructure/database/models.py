"""SQLAlchemy ORM model - khop voi bang events/ticket_types duoc tao trong
migrations/versions/. Day la nguon su that duy nhat cho cau truc bang
(giong quy uoc cua customer-service - moi service tu quan ly schema cua
minh qua Alembic, giong seat-inventory-service).
"""
from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Sequence, String
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

# Sequence rieng cho schema "event", dung de sinh id dang EV001, EV002, ...
# ngay tai tang database - tranh dung id giua nhieu instance/worker cua
# service khi chay voi nhieu uvicorn worker hoac nhieu container.
event_id_seq = Sequence("event_id_seq", start=1, schema="event")


class EventModel(Base):
    __tablename__ = "events"
    __table_args__ = {"schema": "event"}

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    location = Column(String, nullable=False)
    start_time = Column(String, nullable=False)
    status = Column(String, nullable=False, default="DRAFT")
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
    type = Column(String, nullable=False)
    price = Column(Integer, nullable=False)

    event = relationship("EventModel", back_populates="ticket_types")
