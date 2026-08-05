"""SQLAlchemy models for canonical Notification resources."""

from datetime import datetime

from sqlalchemy import DateTime, Integer, Sequence, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


delivery_id_seq = Sequence("delivery_id_seq", start=1, schema="notification")


class DeliveryModel(Base):
    __tablename__ = "deliveries"
    __table_args__ = {"schema": "notification"}

    id: Mapped[str] = mapped_column(String, primary_key=True)
    event_id: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    channel: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False)
    last_error_code: Mapped[str | None] = mapped_column(String, nullable=True)
    to_address: Mapped[str] = mapped_column(String, nullable=False)
    subject: Mapped[str] = mapped_column(String, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    resource_version: Mapped[int] = mapped_column(Integer, nullable=False)


class TemplateModel(Base):
    __tablename__ = "templates"
    __table_args__ = {"schema": "notification"}

    code: Mapped[str] = mapped_column(String, primary_key=True)
    subject: Mapped[str] = mapped_column(String, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    resource_version: Mapped[int] = mapped_column(Integer, nullable=False)
