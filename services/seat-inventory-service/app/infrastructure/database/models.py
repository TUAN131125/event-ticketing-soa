"""SQLAlchemy models for the authoritative PostgreSQL schema."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

SCHEMA = "seat"


class Base(DeclarativeBase):
    pass


class InventoryVersionModel(Base):
    __tablename__ = "inventory_versions"
    __table_args__ = {"schema": SCHEMA}

    event_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    inventory_version: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=1
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("clock_timestamp()"),
    )


class ReservationModel(Base):
    __tablename__ = "reservations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('ACTIVE','CONFIRMED','RELEASED','EXPIRED')",
            name="ck_reservation_status",
        ),
        CheckConstraint("extend_count >= 0", name="ck_reservation_extend_count"),
        UniqueConstraint("booking_id", name="uq_reservation_booking"),
        Index("ix_reservations_status_expiry", "status", "expires_at"),
        Index("ix_reservations_event_status", "event_id", "status"),
        {"schema": SCHEMA},
    )

    reservation_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    booking_id: Mapped[str] = mapped_column(String(128), nullable=False)
    event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    extend_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
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


class SeatModel(Base):
    __tablename__ = "seats"
    __table_args__ = (
        CheckConstraint(
            "status IN ('AVAILABLE','HELD','SOLD','BLOCKED')",
            name="ck_seat_status",
        ),
        CheckConstraint(
            "(status = 'HELD' AND current_reservation_id IS NOT NULL) "
            "OR (status <> 'HELD' AND current_reservation_id IS NULL)",
            name="ck_seat_hold_owner",
        ),
        ForeignKeyConstraint(
            ["current_reservation_id"],
            [f"{SCHEMA}.reservations.reservation_id"],
            name="fk_seat_current_reservation",
            ondelete="RESTRICT",
            use_alter=True,
        ),
        Index("ix_seats_event_status", "event_id", "status"),
        Index(
            "ix_seats_current_reservation",
            "current_reservation_id",
            postgresql_where=text("current_reservation_id IS NOT NULL"),
        ),
        {"schema": SCHEMA},
    )

    event_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    seat_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    section: Mapped[str] = mapped_column(String(80), nullable=False)
    row_label: Mapped[str] = mapped_column(String(40), nullable=False)
    seat_number: Mapped[str] = mapped_column(String(40), nullable=False)
    ticket_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    current_reservation_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True
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


class ReservationItemModel(Base):
    __tablename__ = "reservation_items"
    __table_args__ = (
        ForeignKeyConstraint(
            ["reservation_id"],
            [f"{SCHEMA}.reservations.reservation_id"],
            name="fk_reservation_item_reservation",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["event_id", "seat_id"],
            [f"{SCHEMA}.seats.event_id", f"{SCHEMA}.seats.seat_id"],
            name="fk_reservation_item_seat",
            ondelete="RESTRICT",
        ),
        Index("ix_reservation_items_event_seat", "event_id", "seat_id"),
        {"schema": SCHEMA},
    )

    reservation_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    seat_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("clock_timestamp()"),
    )


class IdempotencyRecordModel(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (
        CheckConstraint(
            "status IN ('COMPLETED')",
            name="ck_idempotency_status",
        ),
        Index("ix_idempotency_expiry", "expires_at"),
        {"schema": SCHEMA},
    )

    scope: Mapped[str] = mapped_column(String(80), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    response_body: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("clock_timestamp()"),
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class SeatAuditModel(Base):
    __tablename__ = "seat_audit"
    __table_args__ = (
        Index("ix_seat_audit_correlation", "correlation_id"),
        Index("ix_seat_audit_reservation_time", "reservation_id", "occurred_at"),
        Index("ix_seat_audit_event_seat_time", "event_id", "seat_id", "occurred_at"),
        {"schema": SCHEMA},
    )

    audit_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    seat_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reservation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    booking_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    operation: Mapped[str] = mapped_column(String(80), nullable=False)
    previous_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    new_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    reason_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    actor_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    caller_service: Mapped[str] = mapped_column(String(128), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    resource_version: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("clock_timestamp()"),
    )
