from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, DateTime, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class WorkflowRow(Base):
    __tablename__ = "workflow"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    public_operation: Mapped[str] = mapped_column(String(80), nullable=False)
    authenticated_subject: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    phase: Mapped[str] = mapped_column(String(40), nullable=False)
    booking_id: Mapped[str | None] = mapped_column(String(128))
    customer_id: Mapped[str | None] = mapped_column(String(128))
    reservation_id: Mapped[str | None] = mapped_column(String(128))
    reservation_version: Mapped[int | None] = mapped_column(Integer)
    payment_id: Mapped[str | None] = mapped_column(String(128))
    payment_status: Mapped[str | None] = mapped_column(String(40))
    ticket_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    total: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)


class WorkflowStepRow(Base):
    __tablename__ = "workflow_step"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workflow_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    step: Mapped[str] = mapped_column(String(100), nullable=False)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    outcome: Mapped[str] = mapped_column(String(40), nullable=False)
    safe_details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class IdempotencyRow(Base):
    __tablename__ = "idempotency_record"
    __table_args__ = (
        UniqueConstraint(
            "operation",
            "authenticated_subject",
            "idempotency_key",
            name="uq_idempotency_scope",
        ),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    operation: Mapped[str] = mapped_column(String(80), nullable=False)
    authenticated_subject: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    workflow_id: Mapped[str] = mapped_column(String(64), nullable=False)
    response_status: Mapped[int | None] = mapped_column(Integer)
    response_body: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class TraceStepRow(Base):
    __tablename__ = "trace_step"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    correlation_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    service: Mapped[str] = mapped_column(String(80), nullable=False)
    operation: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class OutboxRow(Base):
    __tablename__ = "outbox_message"
    message_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workflow_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    destination: Mapped[str] = mapped_column(String(40), nullable=False)
    message_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    state: Mapped[str] = mapped_column(String(30), default="PENDING")
    last_error_code: Mapped[str | None] = mapped_column(String(100))


class ReconciliationRow(Base):
    __tablename__ = "reconciliation_job"
    __table_args__ = (
        UniqueConstraint("workflow_id", "kind", "idempotency_key", name="uq_reconciliation_scope"),
        Index("ix_reconciliation_claimable", "state", "next_attempt_at", "locked_until"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workflow_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(80), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    state: Mapped[str] = mapped_column(String(30), default="PENDING")
    last_evidence: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # Bounds how long the job may keep retrying without inventing an outcome.
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Lease held by the worker replica currently processing this job.
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    extension_count: Mapped[int] = mapped_column(Integer, default=0)
