"""Initial schema - notification schema, id sequence, bang deliveries

Revision ID: 0001
Revises:
Create Date: 2026-07-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS notification")
    op.execute("CREATE SEQUENCE IF NOT EXISTS notification.delivery_id_seq START 1")

    op.create_table(
        "deliveries",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("correlation_id", sa.String(), nullable=False, unique=True),
        sa.Column("to_email", sa.String(), nullable=False),
        sa.Column("subject", sa.String(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="SENT"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        schema="notification",
    )
    # Ghi chu: sa.Column(..., unique=True) o tren da tu tao unique
    # constraint "deliveries_correlation_id_key" - khong can tao them
    # index rieng. Day chinh la hang rao chong gui trung mo ta trong
    # app/domain/rules.py.


def downgrade() -> None:
    op.drop_table("deliveries", schema="notification")
    op.execute("DROP SEQUENCE IF EXISTS notification.delivery_id_seq")
    op.execute("DROP SCHEMA IF EXISTS notification CASCADE")
