"""Create authoritative Identity schema."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0001_identity"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA identity")
    op.create_table(
        "users",
        sa.Column("user_id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("normalized_email", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("token_version", sa.BigInteger(), nullable=False, server_default="1"),
        sa.Column(
            "failed_login_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("locked_until", sa.DateTime(timezone=True)),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE','DISABLED')", name="ck_identity_user_status"
        ),
        sa.CheckConstraint(
            "failed_login_count >= 0", name="ck_identity_failed_login_count"
        ),
        sa.CheckConstraint("token_version >= 1", name="ck_identity_token_version"),
        sa.UniqueConstraint(
            "normalized_email", name="uq_identity_user_normalized_email"
        ),
        schema="identity",
    )
    op.create_index("ix_identity_users_status", "users", ["status"], schema="identity")
    op.create_table(
        "roles",
        sa.Column("role_name", sa.String(40), primary_key=True),
        sa.Column("description", sa.String(200), nullable=False),
        sa.Column(
            "privileged", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
        schema="identity",
    )
    op.create_table(
        "user_roles",
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("role_name", sa.String(40), nullable=False),
        sa.Column("assigned_by", sa.String(36)),
        sa.Column(
            "assigned_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["identity.users.user_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["role_name"], ["identity.roles.role_name"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["assigned_by"], ["identity.users.user_id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("user_id", "role_name"),
        schema="identity",
    )
    op.create_index(
        "ix_identity_user_roles_role", "user_roles", ["role_name"], schema="identity"
    )
    op.create_table(
        "refresh_sessions",
        sa.Column("session_id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("family_id", sa.String(36), nullable=False),
        sa.Column("parent_session_id", sa.String(36)),
        sa.Column("replaced_by_session_id", sa.String(36)),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("revoke_reason", sa.String(80)),
        sa.Column("rotated_at", sa.DateTime(timezone=True)),
        sa.Column("user_agent_hash", sa.String(64)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["identity.users.user_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["parent_session_id"],
            ["identity.refresh_sessions.session_id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["replaced_by_session_id"],
            ["identity.refresh_sessions.session_id"],
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "expires_at > created_at", name="ck_identity_refresh_expiry"
        ),
        sa.UniqueConstraint("token_hash", name="uq_identity_refresh_token_hash"),
        schema="identity",
    )
    op.create_index(
        "ix_identity_refresh_user",
        "refresh_sessions",
        ["user_id", "created_at"],
        schema="identity",
    )
    op.create_index(
        "ix_identity_refresh_family",
        "refresh_sessions",
        ["family_id"],
        schema="identity",
    )
    op.create_index(
        "ix_identity_refresh_expiry",
        "refresh_sessions",
        ["expires_at"],
        schema="identity",
    )
    op.create_index(
        "ix_identity_refresh_active",
        "refresh_sessions",
        ["user_id"],
        schema="identity",
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.create_table(
        "auth_audit",
        sa.Column("audit_id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("result", sa.String(20), nullable=False),
        sa.Column("reason", sa.String(120)),
        sa.Column("actor_id", sa.String(36)),
        sa.Column("target_user_id", sa.String(36)),
        sa.Column("correlation_id", sa.String(128), nullable=False),
        sa.Column("trace_id", sa.String(32), nullable=False),
        sa.Column("ip_hash", sa.String(64)),
        sa.Column(
            "metadata", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
        sa.CheckConstraint(
            "result IN ('SUCCESS','FAILURE','NO_CHANGE')",
            name="ck_identity_audit_result",
        ),
        schema="identity",
    )
    op.create_index(
        "ix_identity_audit_correlation",
        "auth_audit",
        ["correlation_id"],
        schema="identity",
    )
    op.create_index(
        "ix_identity_audit_target_time",
        "auth_audit",
        ["target_user_id", "occurred_at"],
        schema="identity",
    )
    op.create_index(
        "ix_identity_audit_action_time",
        "auth_audit",
        ["action", "occurred_at"],
        schema="identity",
    )
    op.create_table(
        "auth_rate_limits",
        sa.Column("bucket_key", sa.String(64), primary_key=True),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("subject_hash", sa.String(64), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("blocked_until", sa.DateTime(timezone=True)),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
        sa.CheckConstraint("attempts >= 0", name="ck_identity_rate_attempts"),
        schema="identity",
    )
    op.create_index(
        "ix_identity_rate_limit_expiry",
        "auth_rate_limits",
        ["window_started_at", "blocked_until"],
        schema="identity",
    )
    op.bulk_insert(
        sa.table(
            "roles",
            sa.column("role_name", sa.String),
            sa.column("description", sa.String),
            sa.column("privileged", sa.Boolean),
            schema="identity",
        ),
        [
            {
                "role_name": "CUSTOMER",
                "description": "Registered customer",
                "privileged": False,
            },
            {
                "role_name": "ADMIN",
                "description": "Identity and platform administrator",
                "privileged": True,
            },
            {
                "role_name": "CHECKIN_STAFF",
                "description": "Venue check-in staff",
                "privileged": True,
            },
            {
                "role_name": "SERVICE",
                "description": "Authenticated service principal",
                "privileged": True,
            },
        ],
    )


def downgrade() -> None:
    op.execute("DROP SCHEMA identity CASCADE")
