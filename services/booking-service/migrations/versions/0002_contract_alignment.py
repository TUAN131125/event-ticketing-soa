"""Align Booking state with the canonical provider contract.

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_booking_state_consistency", "bookings", schema="booking", type_="check"
    )
    op.drop_constraint("ck_booking_status", "bookings", schema="booking", type_="check")
    op.drop_constraint(
        "ck_booking_payment_status", "bookings", schema="booking", type_="check"
    )
    op.alter_column("bookings", "reservation_id", nullable=True, schema="booking")
    op.alter_column("bookings", "payment_method", nullable=True, schema="booking")
    op.execute(
        "UPDATE booking.bookings SET payment_status = 'CAPTURED' WHERE payment_status = 'SUCCEEDED'"
    )
    op.execute(
        "UPDATE booking.bookings SET payment_status = 'FAILED' WHERE payment_status = 'REFUNDED'"
    )
    op.create_check_constraint(
        "ck_booking_status",
        "bookings",
        "status IN ('PENDING','SEAT_RESERVED','PAYMENT_PROCESSING','CONFIRMED','FAILED','CANCELLED','COMPENSATION_PENDING')",
        schema="booking",
    )
    op.create_check_constraint(
        "ck_booking_payment_status",
        "bookings",
        "payment_status IN ('PENDING','CAPTURED','FAILED','UNKNOWN')",
        schema="booking",
    )
    op.add_column(
        "bookings",
        sa.Column(
            "ticket_ids", postgresql.JSONB(), server_default="[]", nullable=False
        ),
        schema="booking",
    )


def downgrade() -> None:
    op.drop_column("bookings", "ticket_ids", schema="booking")
    op.drop_constraint(
        "ck_booking_payment_status", "bookings", schema="booking", type_="check"
    )
    op.drop_constraint("ck_booking_status", "bookings", schema="booking", type_="check")
    op.execute(
        "UPDATE booking.bookings SET payment_status = 'SUCCEEDED' WHERE payment_status = 'CAPTURED'"
    )
    op.execute(
        "UPDATE booking.bookings SET status = 'FAILED' WHERE status IN ('SEAT_RESERVED','PAYMENT_PROCESSING','COMPENSATION_PENDING')"
    )
    op.create_check_constraint(
        "ck_booking_status",
        "bookings",
        "status IN ('PENDING','CONFIRMED','FAILED','CANCELLED')",
        schema="booking",
    )
    op.create_check_constraint(
        "ck_booking_payment_status",
        "bookings",
        "payment_status IN ('PENDING','SUCCEEDED','FAILED','REFUNDED')",
        schema="booking",
    )
    op.alter_column("bookings", "payment_method", nullable=False, schema="booking")
    op.alter_column("bookings", "reservation_id", nullable=False, schema="booking")
