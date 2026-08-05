"""Authentication audit and rate-limit models."""

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
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.models.base import SCHEMA, Base


class AuthAuditModel(Base):
    __tablename__ = "auth_audit"
    __table_args__ = (
        CheckConstraint(
            "result IN ('SUCCESS','FAILURE','NO_CHANGE')",
            name="ck_identity_audit_result",
        ),
        Index("ix_identity_audit_correlation", "correlation_id"),
        Index(
            "ix_identity_audit_target_time",
            "target_user_id",
            "occurred_at",
        ),
        Index(
            "ix_identity_audit_action_time",
            "action",
            "occurred_at",
        ),
        {"schema": SCHEMA},
    )

    audit_id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    result: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(120), nullable=True)
    actor_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    target_user_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
    )
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    trace_id: Mapped[str] = mapped_column(String(32), nullable=False)
    ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("clock_timestamp()"),
    )


class AuthRateLimitModel(Base):
    __tablename__ = "auth_rate_limits"
    __table_args__ = (
        CheckConstraint(
            "attempts >= 0",
            name="ck_identity_rate_attempts",
        ),
        Index(
            "ix_identity_rate_limit_expiry",
            "window_started_at",
            "blocked_until",
        ),
        {"schema": SCHEMA},
    )

    bucket_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    subject_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    window_started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
    )
    blocked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("clock_timestamp()"),
    )
