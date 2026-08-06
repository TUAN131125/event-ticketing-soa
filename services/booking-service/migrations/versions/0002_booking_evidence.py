"""Add reservation/payment/ticket evidence tracking to bookings.

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "booking"

NEW_STATE_CONSISTENCY_SQL = (
    "(status = 'PENDING' AND reservation_status IN ('RESERVED','CONFIRMED') AND "
    "((payment_status = 'PENDING' AND payment_id IS NULL) OR "
    "(payment_status IN ('PROCESSING','SUCCEEDED','FAILED') "
    "AND payment_id IS NOT NULL))"
    ") OR "
    "(status = 'CONFIRMED' AND reservation_status = 'CONFIRMED' AND "
    "payment_status = 'SUCCEEDED' AND payment_id IS NOT NULL AND "
    "confirmed_at IS NOT NULL AND jsonb_array_length(ticket_ids) > 0) OR "
    "(status = 'FAILED' AND payment_status = 'FAILED' "
    "AND failure_code IS NOT NULL AND failure_reason IS NOT NULL) OR "
    "(status = 'CANCELLED' AND reservation_status = 'RELEASED' "
    "AND cancellation_reason IS NOT NULL AND cancelled_at IS NOT NULL "
    "AND payment_status IN ('PENDING','PROCESSING','FAILED','REFUNDED'))"
)

OLD_STATE_CONSISTENCY_SQL = (
    "(status = 'PENDING' AND payment_status = 'PENDING' "
    "AND payment_id IS NULL) OR "
    "(status = 'CONFIRMED' AND payment_status = 'SUCCEEDED' "
    "AND payment_id IS NOT NULL AND confirmed_at IS NOT NULL) OR "
    "(status = 'FAILED' AND payment_status = 'FAILED' "
    "AND failure_code IS NOT NULL AND failure_reason IS NOT NULL) OR "
    "(status = 'CANCELLED' AND cancellation_reason IS NOT NULL "
    "AND cancelled_at IS NOT NULL "
    "AND payment_status IN ('PENDING','FAILED','REFUNDED'))"
)


def upgrade() -> None:
    op.add_column(
        "bookings",
        sa.Column(
            "reservation_status",
            sa.String(20),
            nullable=False,
            server_default="RESERVED",
        ),
        schema=SCHEMA,
    )
    op.add_column(
        "bookings",
        sa.Column(
            "reservation_confirmed_at", sa.DateTime(timezone=True), nullable=True
        ),
        schema=SCHEMA,
    )
    op.add_column(
        "bookings",
        sa.Column(
            "ticket_ids",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        schema=SCHEMA,
    )
    op.add_column(
        "bookings",
        sa.Column("tickets_attached_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )

    op.create_check_constraint(
        "ck_booking_reservation_status",
        "bookings",
        "reservation_status IN ('RESERVED','CONFIRMED','RELEASED')",
        schema=SCHEMA,
    )

    op.drop_constraint(
        "ck_booking_payment_status", "bookings", schema=SCHEMA, type_="check"
    )
    op.create_check_constraint(
        "ck_booking_payment_status",
        "bookings",
        "payment_status IN ('PENDING','PROCESSING','SUCCEEDED','FAILED','REFUNDED')",
        schema=SCHEMA,
    )

    op.drop_constraint(
        "ck_booking_state_consistency", "bookings", schema=SCHEMA, type_="check"
    )
    op.create_check_constraint(
        "ck_booking_state_consistency",
        "bookings",
        NEW_STATE_CONSISTENCY_SQL,
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_booking_state_consistency", "bookings", schema=SCHEMA, type_="check"
    )
    op.create_check_constraint(
        "ck_booking_state_consistency",
        "bookings",
        OLD_STATE_CONSISTENCY_SQL,
        schema=SCHEMA,
    )

    op.drop_constraint(
        "ck_booking_payment_status", "bookings", schema=SCHEMA, type_="check"
    )
    op.create_check_constraint(
        "ck_booking_payment_status",
        "bookings",
        "payment_status IN ('PENDING','SUCCEEDED','FAILED','REFUNDED')",
        schema=SCHEMA,
    )

    op.drop_constraint(
        "ck_booking_reservation_status", "bookings", schema=SCHEMA, type_="check"
    )

    op.drop_column("bookings", "tickets_attached_at", schema=SCHEMA)
    op.drop_column("bookings", "ticket_ids", schema=SCHEMA)
    op.drop_column("bookings", "reservation_confirmed_at", schema=SCHEMA)
    op.drop_column("bookings", "reservation_status", schema=SCHEMA)
