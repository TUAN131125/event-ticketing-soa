"""Authoritative PostgreSQL models for Booking Service."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

SCHEMA = "booking"


class Base(DeclarativeBase):
    """Declarative base for the booking schema."""


class BookingModel(Base):
    __tablename__ = "bookings"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING','SEAT_RESERVED','PAYMENT_PROCESSING',"
            "'CONFIRMED','FAILED','CANCELLED','COMPENSATION_PENDING')",
            name="ck_booking_status",
        ),
        CheckConstraint(
            "payment_status IN ('PENDING','PROCESSING','SUCCEEDED','FAILED',"
            "'UNKNOWN','REFUND_PENDING','REFUNDED')",
            name="ck_booking_payment_status",
        ),
        CheckConstraint(
            "reservation_status IN ('PENDING','RESERVED','CONFIRMED',"
            "'RELEASE_PENDING','RELEASED','UNKNOWN')",
            name="ck_booking_reservation_status",
        ),
        CheckConstraint(
            "compensation_status IN ('NOT_REQUIRED','PENDING','COMPLETED','FAILED')",
            name="ck_booking_compensation_status",
        ),
        CheckConstraint(
            "compensation_action IN ('NONE','RELEASE_RESERVATION','REFUND_PAYMENT',"
            "'RELEASE_AND_REFUND','RECONCILE_PAYMENT')",
            name="ck_booking_compensation_action",
        ),
        CheckConstraint("total_amount >= 0", name="ck_booking_total_amount"),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="ck_booking_currency"),
        CheckConstraint("resource_version >= 1", name="ck_booking_version"),
        CheckConstraint(
            "(status <> 'PENDING') OR "
            "(reservation_status = 'PENDING' AND payment_status = 'PENDING' "
            "AND payment_id IS NULL AND jsonb_array_length(ticket_ids) = 0)",
            name="ck_booking_pending_evidence",
        ),
        CheckConstraint(
            "(status <> 'SEAT_RESERVED') OR "
            "(reservation_id IS NOT NULL "
            "AND reservation_status IN ('RESERVED','CONFIRMED') "
            "AND payment_status = 'PENDING' AND payment_id IS NULL "
            "AND jsonb_array_length(ticket_ids) = 0)",
            name="ck_booking_seat_reserved_evidence",
        ),
        CheckConstraint(
            "(status <> 'PAYMENT_PROCESSING') OR "
            "(reservation_id IS NOT NULL "
            "AND reservation_status IN ('RESERVED','CONFIRMED') "
            "AND payment_status IN ('PROCESSING','SUCCEEDED','FAILED','UNKNOWN') "
            "AND payment_id IS NOT NULL)",
            name="ck_booking_payment_processing_evidence",
        ),
        CheckConstraint(
            "(status <> 'CONFIRMED') OR "
            "(reservation_status = 'CONFIRMED' AND payment_status = 'SUCCEEDED' "
            "AND payment_id IS NOT NULL AND confirmed_at IS NOT NULL "
            "AND jsonb_array_length(ticket_ids) > 0)",
            name="ck_booking_confirmed_evidence",
        ),
        CheckConstraint(
            "(status <> 'FAILED') OR "
            "(failure_code IS NOT NULL AND failure_reason IS NOT NULL "
            "AND compensation_status IN ('NOT_REQUIRED','COMPLETED'))",
            name="ck_booking_failed_evidence",
        ),
        CheckConstraint(
            "(status <> 'CANCELLED') OR "
            "(cancellation_reason IS NOT NULL AND cancelled_at IS NOT NULL "
            "AND compensation_status IN ('NOT_REQUIRED','COMPLETED'))",
            name="ck_booking_cancelled_evidence",
        ),
        CheckConstraint(
            "(status <> 'COMPENSATION_PENDING') OR "
            "(compensation_status IN ('PENDING','FAILED') "
            "AND intended_terminal_status IN ('FAILED','CANCELLED'))",
            name="ck_booking_compensation_pending_evidence",
        ),
        UniqueConstraint("reservation_id", name="uq_booking_reservation"),
        Index("ix_booking_customer_created", "customer_id", "created_at"),
        Index("ix_booking_event_status", "event_id", "status"),
        Index("ix_booking_status_updated", "status", "updated_at"),
        {"schema": SCHEMA},
    )

    booking_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    customer_id: Mapped[str] = mapped_column(String(128), nullable=False)
    event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    reservation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    payment_method: Mapped[str | None] = mapped_column(String(40), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    payment_status: Mapped[str] = mapped_column(String(30), nullable=False)
    reservation_status: Mapped[str] = mapped_column(String(30), nullable=False)
    compensation_status: Mapped[str] = mapped_column(String(30), nullable=False)
    compensation_action: Mapped[str] = mapped_column(String(40), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    payment_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    payment_provider_reference: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )
    compensation_provider_reference: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )
    payment_failure_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    compensation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    intended_terminal_status: Mapped[str | None] = mapped_column(
        String(30), nullable=True
    )
    reservation_version: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    ticket_ids: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    resource_version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("clock_timestamp()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("clock_timestamp()"),
    )
    reservation_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reservation_confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reservation_released_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    payment_recorded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    payment_refunded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    compensation_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    tickets_attached_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    items: Mapped[list["BookingItemModel"]] = relationship(
        back_populates="booking",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="BookingItemModel.seat_id",
    )


class BookingItemModel(Base):
    __tablename__ = "booking_items"
    __table_args__ = (
        CheckConstraint("unit_price >= 0", name="ck_booking_item_price"),
        {"schema": SCHEMA},
    )

    booking_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey(f"{SCHEMA}.bookings.booking_id", ondelete="CASCADE"),
        primary_key=True,
    )
    seat_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    ticket_type: Mapped[str] = mapped_column(String(128), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("clock_timestamp()"),
    )

    booking: Mapped[BookingModel] = relationship(back_populates="items")


class IdempotencyRecordModel(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (
        CheckConstraint("status = 'COMPLETED'", name="ck_booking_idempotency_status"),
        CheckConstraint(
            "expires_at > created_at", name="ck_booking_idempotency_expiry"
        ),
        Index("ix_booking_idempotency_expiry", "expires_at"),
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


class BookingAuditModel(Base):
    __tablename__ = "booking_audit"
    __table_args__ = (
        CheckConstraint("resource_version >= 1", name="ck_booking_audit_version"),
        UniqueConstraint(
            "booking_id", "resource_version", name="uq_booking_audit_version"
        ),
        Index("ix_booking_audit_booking_time", "booking_id", "occurred_at"),
        Index("ix_booking_audit_correlation", "correlation_id"),
        {"schema": SCHEMA},
    )

    audit_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    booking_id: Mapped[str] = mapped_column(String(32), nullable=False)
    operation: Mapped[str] = mapped_column(String(80), nullable=False)
    previous_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    new_status: Mapped[str] = mapped_column(String(30), nullable=False)
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
        CheckConstraint("aggregate_version >= 1", name="ck_booking_outbox_version"),
        CheckConstraint("publish_attempts >= 0", name="ck_booking_outbox_attempts"),
        UniqueConstraint(
            "aggregate_id",
            "aggregate_version",
            name="uq_booking_outbox_aggregate_version",
        ),
        Index(
            "ix_booking_outbox_unpublished",
            "occurred_at",
            postgresql_where=text("published_at IS NULL"),
        ),
        {"schema": SCHEMA},
    )

    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    aggregate_id: Mapped[str] = mapped_column(String(32), nullable=False)
    aggregate_type: Mapped[str] = mapped_column(
        String(40), nullable=False, server_default="Booking"
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
