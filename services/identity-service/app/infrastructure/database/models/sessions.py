"""Refresh-session models."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.models.base import SCHEMA, Base


class RefreshSessionModel(Base):
    __tablename__ = "refresh_sessions"
    __table_args__ = (
        CheckConstraint(
            "expires_at > created_at",
            name="ck_identity_refresh_expiry",
        ),
        UniqueConstraint(
            "token_hash",
            name="uq_identity_refresh_token_hash",
        ),
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
        DateTime(timezone=True),
        nullable=False,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    revoke_reason: Mapped[str | None] = mapped_column(
        String(80),
        nullable=True,
    )
    rotated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    user_agent_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("clock_timestamp()"),
    )
