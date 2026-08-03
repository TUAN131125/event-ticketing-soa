"""Authoritative PostgreSQL models for Payment Service."""

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
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

SCHEMA = "payment"


class Base(DeclarativeBase):
    """Declarative base for the payment schema."""


class PaymentModel(Base):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING','AUTHORIZED','CAPTURED','FAILED','CANCELLED',"
            "'PARTIALLY_REFUNDED','REFUNDED')",
            name="ck_payment_status",
        ),
        CheckConstraint("amount > 0", name="ck_payment_amount"),
        CheckConstraint("captured_amount >= 0", name="ck_payment_captured_amount"),
        CheckConstraint("refunded_amount >= 0", name="ck_payment_refunded_amount"),
        CheckConstraint("captured_amount <= amount", name="ck_payment_captured_limit"),
        CheckConstraint(
            "refunded_amount <= captured_amount", name="ck_payment_refunded_limit"
        ),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="ck_payment_currency"),
        CheckConstraint("resource_version >= 1", name="ck_payment_version"),
        CheckConstraint(
            "(status = 'PENDING' AND captured_amount = 0 AND refunded_amount = 0) OR "
            "(status = 'AUTHORIZED' AND provider_reference IS NOT NULL "
            "AND authorized_at IS NOT NULL AND captured_amount = 0 "
            "AND refunded_amount = 0) OR "
            "(status = 'CAPTURED' AND provider_reference IS NOT NULL "
            "AND captured_at IS NOT NULL AND captured_amount = amount "
            "AND refunded_amount = 0) OR "
            "(status = 'FAILED' AND failure_code IS NOT NULL "
            "AND failure_reason IS NOT NULL AND captured_amount = 0 "
            "AND refunded_amount = 0) OR "
            "(status = 'CANCELLED' AND cancellation_reason IS NOT NULL "
            "AND cancelled_at IS NOT NULL AND captured_amount = 0 "
            "AND refunded_amount = 0) OR "
            "(status = 'PARTIALLY_REFUNDED' AND captured_amount = amount "
            "AND refunded_amount > 0 AND refunded_amount < amount) OR "
            "(status = 'REFUNDED' AND captured_amount = amount "
            "AND refunded_amount = amount AND refunded_at IS NOT NULL)",
            name="ck_payment_state_consistency",
        ),
        UniqueConstraint("booking_id", name="uq_payment_booking"),
        UniqueConstraint(
            "provider", "provider_reference", name="uq_payment_provider_reference"
        ),
        Index("ix_payment_customer_created", "customer_id", "created_at"),
        Index("ix_payment_status_created", "status", "created_at"),
        Index("ix_payment_provider_status", "provider", "status"),
        {"schema": SCHEMA},
    )

    payment_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    booking_id: Mapped[str] = mapped_column(String(128), nullable=False)
    customer_id: Mapped[str] = mapped_column(String(128), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    payment_method: Mapped[str] = mapped_column(String(40), nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    captured_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    refunded_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    failure_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
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
    authorized_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    captured_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    refunded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class RefundModel(Base):
    __tablename__ = "refunds"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_refund_amount"),
        CheckConstraint(
            "kind IN ('REQUESTED','RECONCILIATION')", name="ck_refund_kind"
        ),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="ck_refund_currency"),
        UniqueConstraint("payment_id", "idempotency_key", name="uq_refund_payment_key"),
        UniqueConstraint(
            "provider", "provider_reference", name="uq_refund_provider_reference"
        ),
        Index("ix_refund_payment_created", "payment_id", "created_at"),
        {"schema": SCHEMA},
    )

    refund_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    payment_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey(f"{SCHEMA}.payments.payment_id", ondelete="RESTRICT"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_reference: Mapped[str] = mapped_column(String(128), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("clock_timestamp()"),
    )


class IdempotencyRecordModel(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (
        CheckConstraint("status = 'COMPLETED'", name="ck_payment_idempotency_status"),
        CheckConstraint(
            "expires_at > created_at", name="ck_payment_idempotency_expiry"
        ),
        Index("ix_payment_idempotency_expiry", "expires_at"),
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


class PaymentAuditModel(Base):
    __tablename__ = "payment_audit"
    __table_args__ = (
        CheckConstraint("resource_version >= 1", name="ck_payment_audit_version"),
        UniqueConstraint(
            "payment_id", "resource_version", name="uq_payment_audit_version"
        ),
        Index("ix_payment_audit_payment_time", "payment_id", "occurred_at"),
        Index("ix_payment_audit_correlation", "correlation_id"),
        {"schema": SCHEMA},
    )

    audit_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    payment_id: Mapped[str] = mapped_column(String(32), nullable=False)
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
        CheckConstraint("aggregate_version >= 1", name="ck_payment_outbox_version"),
        CheckConstraint("publish_attempts >= 0", name="ck_payment_outbox_attempts"),
        UniqueConstraint(
            "aggregate_id",
            "aggregate_version",
            name="uq_payment_outbox_aggregate_version",
        ),
        Index(
            "ix_payment_outbox_unpublished",
            "occurred_at",
            postgresql_where=text("published_at IS NULL"),
        ),
        {"schema": SCHEMA},
    )

    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    aggregate_id: Mapped[str] = mapped_column(String(32), nullable=False)
    aggregate_type: Mapped[str] = mapped_column(
        String(40), nullable=False, server_default="Payment"
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
