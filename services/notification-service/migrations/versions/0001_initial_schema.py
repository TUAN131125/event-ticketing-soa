"""Initial schema - khop bang notification.* trong SQL baseline chinh
thuc (Giai doan 5, contracts/sql/001_baseline.sql): inbound_events,
deliveries, delivery_attempts, templates. Hat giong 4 template mac dinh
(NOT-09) de PUT /templates/{code} luon co du lieu de doc/so sanh If-Match
ngay tu dau, khong phu thuoc fallback file tinh.

Revision ID: 0001
Revises:
Create Date: 2026-07-31
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DEFAULT_TEMPLATES = [
    (
        "booking_confirmed",
        "Dat ve thanh cong",
        "<h2>Dat ve thanh cong!</h2>\n"
        "<p>Xin chao {customer_name},</p>\n"
        "<p>Booking <strong>{booking_id}</strong> cua ban da duoc xac nhan.</p>\n"
        "<p>Ma ve: {ticket_ids}</p>\n",
    ),
    (
        "booking_failed",
        "Dat ve khong thanh cong",
        "<h2>Dat ve khong thanh cong</h2>\n"
        "<p>Booking <strong>{booking_id}</strong> khong the hoan tat.</p>\n"
        "<p>Ly do: {reason}</p>\n",
    ),
    (
        "event_changed",
        "Su kien thay doi",
        "<h2>Su kien thay doi</h2>\n"
        "<p>Su kien <strong>{event_id}</strong> vua duoc cap nhat.</p>\n"
        "<p>Chi tiet: {change_summary}</p>\n",
    ),
    (
        "ticket_issued",
        "Ve dien tu da duoc phat hanh",
        "<h2>Ve dien tu da duoc phat hanh</h2>\n"
        "<p>Ve <strong>{ticket_id}</strong> cho su kien <strong>{event_id}</strong> da san sang.</p>\n"
        "<p>Vui long kiem tra ung dung/email de xem ma QR check-in.</p>\n",
    ),
]


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS notification")
    op.execute("CREATE SEQUENCE IF NOT EXISTS notification.delivery_id_seq START 1")

    op.create_table(
        "inbound_events",
        sa.Column("event_id", sa.String(40), primary_key=True),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("correlation_id", sa.String(64), nullable=False),
        sa.Column("aggregate_id", sa.String(64), nullable=False),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema="notification",
    )

    op.create_table(
        "deliveries",
        sa.Column("delivery_id", sa.String(40), primary_key=True),
        sa.Column(
            "event_id",
            sa.String(40),
            sa.ForeignKey("notification.inbound_events.event_id"),
            nullable=False,
        ),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("destination_hash", sa.String(64), nullable=False),
        sa.Column(
            "status",
            sa.String(30),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "status IN ('PENDING','SENDING','DELIVERED','RETRY_PENDING','DEAD_LETTER','CANCELLED')",
            name="ck_deliveries_status",
        ),
        sa.CheckConstraint("channel IN ('EMAIL','SMS')", name="ck_deliveries_channel"),
        schema="notification",
    )

    op.create_table(
        "delivery_attempts",
        sa.Column(
            "delivery_id",
            sa.String(40),
            sa.ForeignKey("notification.deliveries.delivery_id"),
            primary_key=True,
        ),
        sa.Column("attempt_no", sa.Integer(), primary_key=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error_code", sa.String(80), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema="notification",
    )

    op.create_table(
        "templates",
        sa.Column("template_code", sa.String(80), primary_key=True),
        sa.Column("subject", sa.String(200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("resource_version", sa.BigInteger(), nullable=False, server_default="1"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("resource_version > 0", name="ck_templates_resource_version"),
        schema="notification",
    )

    templates_table = sa.table(
        "templates",
        sa.column("template_code", sa.String),
        sa.column("subject", sa.String),
        sa.column("body", sa.Text),
        schema="notification",
    )
    op.bulk_insert(
        templates_table,
        [{"template_code": code, "subject": subject, "body": body} for code, subject, body in DEFAULT_TEMPLATES],
    )


def downgrade() -> None:
    op.drop_table("delivery_attempts", schema="notification")
    op.drop_table("deliveries", schema="notification")
    op.drop_table("templates", schema="notification")
    op.drop_table("inbound_events", schema="notification")
    op.execute("DROP SEQUENCE IF EXISTS notification.delivery_id_seq")
    op.execute("DROP SCHEMA IF EXISTS notification CASCADE")
