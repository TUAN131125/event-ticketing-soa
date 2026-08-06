"""Protect intermediate Booking state evidence in PostgreSQL.

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-06
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "booking"


def upgrade() -> None:
    op.create_check_constraint(
        "ck_booking_pending_evidence",
        "bookings",
        "(status <> 'PENDING') OR "
        "(reservation_status = 'PENDING' AND payment_status = 'PENDING' "
        "AND payment_id IS NULL AND jsonb_array_length(ticket_ids) = 0)",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_booking_seat_reserved_evidence",
        "bookings",
        "(status <> 'SEAT_RESERVED') OR "
        "(reservation_id IS NOT NULL "
        "AND reservation_status IN ('RESERVED','CONFIRMED') "
        "AND payment_status = 'PENDING' AND payment_id IS NULL "
        "AND jsonb_array_length(ticket_ids) = 0)",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_booking_payment_processing_evidence",
        "bookings",
        "(status <> 'PAYMENT_PROCESSING') OR "
        "(reservation_id IS NOT NULL "
        "AND reservation_status IN ('RESERVED','CONFIRMED') "
        "AND payment_status IN ('PROCESSING','SUCCEEDED','FAILED','UNKNOWN') "
        "AND payment_id IS NOT NULL)",
        schema=SCHEMA,
    )


def downgrade() -> None:
    for name in (
        "ck_booking_payment_processing_evidence",
        "ck_booking_seat_reserved_evidence",
        "ck_booking_pending_evidence",
    ):
        op.drop_constraint(name, "bookings", schema=SCHEMA, type_="check")
