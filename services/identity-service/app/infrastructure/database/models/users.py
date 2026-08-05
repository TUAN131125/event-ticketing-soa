"""Identity account and role models."""

from __future__ import annotations

from datetime import datetime

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
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.models.base import SCHEMA, Base


class UserModel(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "status IN ('ACTIVE','DISABLED')",
            name="ck_identity_user_status",
        ),
        CheckConstraint(
            "failed_login_count >= 0",
            name="ck_identity_failed_login_count",
        ),
        CheckConstraint(
            "token_version >= 1",
            name="ck_identity_token_version",
        ),
        UniqueConstraint(
            "normalized_email",
            name="uq_identity_user_normalized_email",
        ),
        Index("ix_identity_users_status", "status"),
        {"schema": SCHEMA},
    )

    user_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    normalized_email: Mapped[str] = mapped_column(String(320), nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default="ACTIVE",
    )
    token_version: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        server_default="1",
    )
    failed_login_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
    )
    locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
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
    privileged: Mapped[bool] = mapped_column(
        nullable=False,
        server_default="false",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("clock_timestamp()"),
    )


class UserRoleModel(Base):
    __tablename__ = "user_roles"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "role_name",
            name="uq_identity_user_role",
        ),
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
