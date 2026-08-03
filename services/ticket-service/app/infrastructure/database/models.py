"""Authoritative PostgreSQL models for Ticket Service."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

SCHEMA = "ticket"


class Base(DeclarativeBase):
    """Declarative base for the ticket schema."""


class TicketModel(Base):
    __tablename__ = "tickets"
    __table_args__ = (
        CheckConstraint(
            "status IN ('VALID','CHECKED_IN','CANCELLED')",
            name="ck_ticket_status",
        ),
        CheckConstraint("qr_version >= 1", name="ck_ticket_qr_version"),
        CheckConstraint("resource_version >= 1", name="ck_ticket_version"),
        CheckConstraint(
            "(status = 'VALID' AND checked_in_at IS NULL "
            "AND checked_in_gate_id IS NULL AND checked_in_by IS NULL "
            "AND cancelled_at IS NULL AND cancellation_reason IS NULL) OR "
            "(status = 'CHECKED_IN' AND checked_in_at IS NOT NULL "
            "AND checked_in_gate_id IS NOT NULL AND checked_in_by IS NOT NULL "
            "AND cancelled_at IS NULL AND cancellation_reason IS NULL) OR "
            "(status = 'CANCELLED' AND checked_in_at IS NULL "
            "AND checked_in_gate_id IS NULL AND checked_in_by IS NULL "
            "AND cancelled_at IS NOT NULL AND cancellation_reason IS NOT NULL)",
            name="ck_ticket_state_consistency",
        ),
        UniqueConstraint("booking_id", "seat_id", name="uq_ticket_booking_seat"),
        Index(
            "uq_ticket_active_event_seat",
            "event_id",
            "seat_id",
            unique=True,
            postgresql_where=text("status <> 'CANCELLED'"),
        ),
        Index("ix_ticket_booking", "booking_id", "ticket_id"),
        Index("ix_ticket_customer_issued", "customer_id", "issued_at"),
        Index("ix_ticket_event_status", "event_id", "status"),
        {"schema": SCHEMA},
    )

    ticket_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    booking_id: Mapped[str] = mapped_column(String(128), nullable=False)
    customer_id: Mapped[str] = mapped_column(String(128), nullable=False)
    event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    payment_id: Mapped[str] = mapped_column(String(128), nullable=False)
    seat_id: Mapped[str] = mapped_column(String(128), nullable=False)
    seat_label: Mapped[str] = mapped_column(String(128), nullable=False)
    ticket_type: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    qr_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    resource_version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("clock_timestamp()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("clock_timestamp()"),
    )
    checked_in_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    checked_in_gate_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    checked_in_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class IdempotencyRecordModel(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (
        CheckConstraint("status = 'COMPLETED'", name="ck_ticket_idempotency_status"),
        CheckConstraint("expires_at > created_at", name="ck_ticket_idempotency_expiry"),
        Index("ix_ticket_idempotency_expiry", "expires_at"),
        {"schema": SCHEMA},
    )

    scope: Mapped[str] = mapped_column(String(80), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    response_body: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class TicketAuditModel(Base):
    __tablename__ = "ticket_audit"
    __table_args__ = (
        CheckConstraint("resource_version >= 1", name="ck_ticket_audit_version"),
        UniqueConstraint(
            "ticket_id", "resource_version", name="uq_ticket_audit_version"
        ),
        Index("ix_ticket_audit_ticket_time", "ticket_id", "occurred_at"),
        Index("ix_ticket_audit_correlation", "correlation_id"),
        {"schema": SCHEMA},
    )

    audit_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    ticket_id: Mapped[str] = mapped_column(String(32), nullable=False)
    operation: Mapped[str] = mapped_column(String(80), nullable=False)
    previous_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    new_status: Mapped[str] = mapped_column(String(20), nullable=False)
    caller_service: Mapped[str] = mapped_column(String(128), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    resource_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("clock_timestamp()"),
    )


class OutboxEventModel(Base):
    __tablename__ = "outbox_events"
    __table_args__ = (
        CheckConstraint("aggregate_version >= 1", name="ck_ticket_outbox_version"),
        CheckConstraint("publish_attempts >= 0", name="ck_ticket_outbox_attempts"),
        UniqueConstraint(
            "aggregate_id",
            "aggregate_version",
            name="uq_ticket_outbox_aggregate_version",
        ),
        Index(
            "ix_ticket_outbox_unpublished",
            "occurred_at",
            postgresql_where=text("published_at IS NULL"),
        ),
        {"schema": SCHEMA},
    )

    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    aggregate_id: Mapped[str] = mapped_column(String(32), nullable=False)
    aggregate_type: Mapped[str] = mapped_column(
        String(40), nullable=False, server_default="Ticket"
    )
    aggregate_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    publish_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
