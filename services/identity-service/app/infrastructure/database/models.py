"""Authoritative PostgreSQL models for identity, sessions and audit."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

SCHEMA = "identity"


class Base(DeclarativeBase):
    """Base class for all identity schema models."""


class UserModel(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "status IN ('ACTIVE','DISABLED')", name="ck_identity_user_status"
        ),
        CheckConstraint(
            "failed_login_count >= 0", name="ck_identity_failed_login_count"
        ),
        CheckConstraint("token_version >= 1", name="ck_identity_token_version"),
        UniqueConstraint("normalized_email", name="uq_identity_user_normalized_email"),
        Index("ix_identity_users_status", "status"),
        {"schema": SCHEMA},
    )

    user_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    normalized_email: Mapped[str] = mapped_column(String(320), nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="ACTIVE"
    )
    token_version: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="1"
    )
    failed_login_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
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


class RoleModel(Base):
    __tablename__ = "roles"
    __table_args__ = {"schema": SCHEMA}

    role_name: Mapped[str] = mapped_column(String(40), primary_key=True)
    description: Mapped[str] = mapped_column(String(200), nullable=False)
    privileged: Mapped[bool] = mapped_column(nullable=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("clock_timestamp()"),
    )


class UserRoleModel(Base):
    __tablename__ = "user_roles"
    __table_args__ = (
        UniqueConstraint("user_id", "role_name", name="uq_identity_user_role"),
        Index("ix_identity_user_roles_role", "role_name"),
        {"schema": SCHEMA},
    )

    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey(f"{SCHEMA}.users.user_id", ondelete="CASCADE"),
        primary_key=True,
    )
    role_name: Mapped[str] = mapped_column(
        String(40),
        ForeignKey(f"{SCHEMA}.roles.role_name", ondelete="RESTRICT"),
        primary_key=True,
    )
    assigned_by: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey(f"{SCHEMA}.users.user_id", ondelete="SET NULL"),
        nullable=True,
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("clock_timestamp()"),
    )


class RefreshSessionModel(Base):
    __tablename__ = "refresh_sessions"
    __table_args__ = (
        CheckConstraint("expires_at > created_at", name="ck_identity_refresh_expiry"),
        UniqueConstraint("token_hash", name="uq_identity_refresh_token_hash"),
        Index("ix_identity_refresh_user", "user_id", "created_at"),
        Index("ix_identity_refresh_family", "family_id"),
        Index("ix_identity_refresh_expiry", "expires_at"),
        Index(
            "ix_identity_refresh_active",
            "user_id",
            postgresql_where=text("revoked_at IS NULL"),
        ),
        {"schema": SCHEMA},
    )

    session_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey(f"{SCHEMA}.users.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    family_id: Mapped[str] = mapped_column(String(36), nullable=False)
    parent_session_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey(
            f"{SCHEMA}.refresh_sessions.session_id",
            ondelete="SET NULL",
            use_alter=True,
        ),
        nullable=True,
    )
    replaced_by_session_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey(
            f"{SCHEMA}.refresh_sessions.session_id",
            ondelete="SET NULL",
            use_alter=True,
        ),
        nullable=True,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoke_reason: Mapped[str | None] = mapped_column(String(80), nullable=True)
    rotated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    user_agent_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("clock_timestamp()"),
    )


class AuthAuditModel(Base):
    __tablename__ = "auth_audit"
    __table_args__ = (
        CheckConstraint(
            "result IN ('SUCCESS','FAILURE','NO_CHANGE')",
            name="ck_identity_audit_result",
        ),
        Index("ix_identity_audit_correlation", "correlation_id"),
        Index("ix_identity_audit_target_time", "target_user_id", "occurred_at"),
        Index("ix_identity_audit_action_time", "action", "occurred_at"),
        {"schema": SCHEMA},
    )

    audit_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    result: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(120), nullable=True)
    actor_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    target_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    trace_id: Mapped[str] = mapped_column(String(32), nullable=False)
    ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("clock_timestamp()"),
    )


class AuthRateLimitModel(Base):
    __tablename__ = "auth_rate_limits"
    __table_args__ = (
        CheckConstraint("attempts >= 0", name="ck_identity_rate_attempts"),
        Index("ix_identity_rate_limit_expiry", "window_started_at", "blocked_until"),
        {"schema": SCHEMA},
    )

    bucket_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    subject_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    window_started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    blocked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("clock_timestamp()"),
    )
