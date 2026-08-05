"""Align Notification persistence with canonical deliveries and templates.

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "deliveries",
        "correlation_id",
        new_column_name="event_id",
        schema="notification",
    )
    op.alter_column(
        "deliveries", "to_email", new_column_name="to_address", schema="notification"
    )
    op.alter_column(
        "deliveries", "type", new_column_name="channel", schema="notification"
    )
    op.add_column(
        "deliveries",
        sa.Column("attempt_count", sa.Integer(), server_default="1", nullable=False),
        schema="notification",
    )
    op.add_column(
        "deliveries", sa.Column("last_error_code", sa.String()), schema="notification"
    )
    op.add_column(
        "deliveries",
        sa.Column("resource_version", sa.Integer(), server_default="1", nullable=False),
        schema="notification",
    )
    op.execute(
        "UPDATE notification.deliveries SET channel = 'EMAIL', status = 'DELIVERED'"
    )
    op.create_table(
        "templates",
        sa.Column("code", sa.String(), primary_key=True),
        sa.Column("subject", sa.String(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("resource_version", sa.Integer(), nullable=False),
        schema="notification",
    )


def downgrade() -> None:
    op.drop_table("templates", schema="notification")
    op.drop_column("deliveries", "resource_version", schema="notification")
    op.drop_column("deliveries", "last_error_code", schema="notification")
    op.drop_column("deliveries", "attempt_count", schema="notification")
    op.alter_column(
        "deliveries", "channel", new_column_name="type", schema="notification"
    )
    op.alter_column(
        "deliveries", "to_address", new_column_name="to_email", schema="notification"
    )
    op.alter_column(
        "deliveries",
        "event_id",
        new_column_name="correlation_id",
        schema="notification",
    )
