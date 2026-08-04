"""SQLAlchemy ORM model - khop voi 4 bang trong SQL baseline chinh thuc
(Giai doan 5, sql/001_baseline.sql, schema "notification"):
inbound_events, deliveries, delivery_attempts, templates."""
from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Sequence,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base

Base = declarative_base()

delivery_id_seq = Sequence("delivery_id_seq", start=1, schema="notification")

UQ_TEMPLATE_CODE = "templates_pkey"  # PK, khong can constraint rieng


class InboundEventModel(Base):
    __tablename__ = "inbound_events"
    __table_args__ = {"schema": "notification"}

    event_id = Column(String(40), primary_key=True)
    event_type = Column(String(100), nullable=False)
    schema_version = Column(Integer, nullable=False)
    correlation_id = Column(String(64), nullable=False)
    aggregate_id = Column(String(64), nullable=False)
    payload = Column(JSONB, nullable=False)
    received_at = Column(DateTime(timezone=True), nullable=False)


class DeliveryModel(Base):
    __tablename__ = "deliveries"
    __table_args__ = {"schema": "notification"}

    delivery_id = Column(String(40), primary_key=True)
    event_id = Column(
        String(40),
        ForeignKey("notification.inbound_events.event_id"),
        nullable=False,
    )
    channel = Column(String(20), nullable=False)
    destination_hash = Column(String(64), nullable=False)
    status = Column(String(30), nullable=False)
    attempt_count = Column(Integer, nullable=False, default=0)
    next_attempt_at = Column(DateTime(timezone=True), nullable=True)
    last_error_code = Column(String(80), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)


class DeliveryAttemptModel(Base):
    __tablename__ = "delivery_attempts"
    __table_args__ = {"schema": "notification"}

    delivery_id = Column(
        String(40),
        ForeignKey("notification.deliveries.delivery_id"),
        primary_key=True,
    )
    attempt_no = Column(Integer, primary_key=True)
    status = Column(String(20), nullable=False)
    error_code = Column(String(80), nullable=True)
    occurred_at = Column(DateTime(timezone=True), nullable=False)


class TemplateModel(Base):
    __tablename__ = "templates"
    __table_args__ = {"schema": "notification"}

    template_code = Column(String(80), primary_key=True)
    subject = Column(String(200), nullable=False)
    body = Column(Text, nullable=False)
    resource_version = Column(BigInteger, nullable=False, default=1)
    updated_at = Column(DateTime(timezone=True), nullable=False)
