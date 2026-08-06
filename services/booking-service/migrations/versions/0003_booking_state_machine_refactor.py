"""Expand Booking state machine and compensation evidence.

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "booking"


def upgrade() -> None:
    # Existing clients created bookings with reservation/payment metadata at
    # creation time.  The canonical v2 contract attaches those references
    # later, therefore both columns become nullable without dropping them.
    op.alter_column("bookings", "reservation_id", nullable=True, schema=SCHEMA)
    op.alter_column("bookings", "payment_method", nullable=True, schema=SCHEMA)
    op.alter_column(
        "bookings",
        "status",
        type_=sa.String(30),
        existing_type=sa.String(20),
        schema=SCHEMA,
    )
    op.alter_column(
        "bookings",
        "payment_status",
        type_=sa.String(30),
        existing_type=sa.String(20),
        schema=SCHEMA,
    )
    op.alter_column(
        "bookings",
        "reservation_status",
        type_=sa.String(30),
        existing_type=sa.String(20),
        schema=SCHEMA,
    )
    op.alter_column(
        "booking_audit",
        "previous_status",
        type_=sa.String(30),
        existing_type=sa.String(20),
        schema=SCHEMA,
    )
    op.alter_column(
        "booking_audit",
        "new_status",
        type_=sa.String(30),
        existing_type=sa.String(20),
        schema=SCHEMA,
    )

    columns = (
        sa.Column(
            "compensation_status",
            sa.String(30),
            nullable=False,
            server_default="NOT_REQUIRED",
        ),
        sa.Column(
            "compensation_action",
            sa.String(40),
            nullable=False,
            server_default="NONE",
        ),
        sa.Column("compensation_reason", sa.Text(), nullable=True),
        sa.Column("intended_terminal_status", sa.String(30), nullable=True),
        sa.Column("reservation_version", sa.BigInteger(), nullable=True),
        sa.Column("reservation_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reservation_released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payment_provider_reference", sa.String(128), nullable=True),
        sa.Column("compensation_provider_reference", sa.String(128), nullable=True),
        sa.Column("payment_failure_code", sa.String(128), nullable=True),
        sa.Column("payment_recorded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payment_refunded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("compensation_updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    for column in columns:
        op.add_column("bookings", column, schema=SCHEMA)

    # Remove the v1 checks before converting legacy PENDING rows to the
    # explicit v2 intermediate states.  No downstream outcome is fabricated:
    # the conversion uses only reservation/payment evidence already persisted.
    for name in (
        "ck_booking_state_consistency",
        "ck_booking_status",
        "ck_booking_payment_status",
        "ck_booking_reservation_status",
    ):
        op.drop_constraint(name, "bookings", schema=SCHEMA, type_="check")

    op.execute(
        "UPDATE booking.bookings SET reservation_status = 'PENDING' "
        "WHERE reservation_id IS NULL"
    )
    op.execute(
        "UPDATE booking.bookings SET status = CASE "
        "WHEN payment_id IS NOT NULL "
        "OR payment_status IN ('PROCESSING','SUCCEEDED','FAILED') "
        "THEN 'PAYMENT_PROCESSING' "
        "WHEN reservation_id IS NOT NULL THEN 'SEAT_RESERVED' "
        "ELSE 'PENDING' END "
        "WHERE status = 'PENDING'"
    )

    op.create_check_constraint(
        "ck_booking_status",
        "bookings",
        "status IN ('PENDING','SEAT_RESERVED','PAYMENT_PROCESSING','CONFIRMED',"
        "'FAILED','CANCELLED','COMPENSATION_PENDING')",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_booking_payment_status",
        "bookings",
        "payment_status IN ('PENDING','PROCESSING','SUCCEEDED','FAILED','UNKNOWN',"
        "'REFUND_PENDING','REFUNDED')",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_booking_reservation_status",
        "bookings",
        "reservation_status IN ('PENDING','RESERVED','CONFIRMED','RELEASE_PENDING',"
        "'RELEASED','UNKNOWN')",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_booking_compensation_status",
        "bookings",
        "compensation_status IN ('NOT_REQUIRED','PENDING','COMPLETED','FAILED')",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_booking_compensation_action",
        "bookings",
        "compensation_action IN ('NONE','RELEASE_RESERVATION','REFUND_PAYMENT',"
        "'RELEASE_AND_REFUND','RECONCILE_PAYMENT')",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_booking_confirmed_evidence",
        "bookings",
        "(status <> 'CONFIRMED') OR (reservation_status = 'CONFIRMED' "
        "AND payment_status = 'SUCCEEDED' AND payment_id IS NOT NULL "
        "AND confirmed_at IS NOT NULL AND jsonb_array_length(ticket_ids) > 0)",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_booking_failed_evidence",
        "bookings",
        "(status <> 'FAILED') OR (failure_code IS NOT NULL "
        "AND failure_reason IS NOT NULL "
        "AND compensation_status IN ('NOT_REQUIRED','COMPLETED'))",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_booking_cancelled_evidence",
        "bookings",
        "(status <> 'CANCELLED') OR (cancellation_reason IS NOT NULL "
        "AND cancelled_at IS NOT NULL "
        "AND compensation_status IN ('NOT_REQUIRED','COMPLETED'))",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_booking_compensation_pending_evidence",
        "bookings",
        "(status <> 'COMPENSATION_PENDING') OR "
        "(compensation_status IN ('PENDING','FAILED') "
        "AND intended_terminal_status IN ('FAILED','CANCELLED'))",
        schema=SCHEMA,
    )

    op.drop_index("ix_booking_status_created", table_name="bookings", schema=SCHEMA)
    op.create_index(
        "ix_booking_status_updated", "bookings", ["status", "updated_at"], schema=SCHEMA
    )


def downgrade() -> None:
    op.drop_index("ix_booking_status_updated", table_name="bookings", schema=SCHEMA)
    op.create_index(
        "ix_booking_status_created", "bookings", ["status", "created_at"], schema=SCHEMA
    )
    for name in (
        "ck_booking_compensation_pending_evidence",
        "ck_booking_cancelled_evidence",
        "ck_booking_failed_evidence",
        "ck_booking_confirmed_evidence",
        "ck_booking_compensation_action",
        "ck_booking_compensation_status",
        "ck_booking_reservation_status",
        "ck_booking_payment_status",
        "ck_booking_status",
    ):
        op.drop_constraint(name, "bookings", schema=SCHEMA, type_="check")

    op.create_check_constraint(
        "ck_booking_status",
        "bookings",
        "status IN ('PENDING','CONFIRMED','FAILED','CANCELLED')",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_booking_payment_status",
        "bookings",
        "payment_status IN ('PENDING','PROCESSING','SUCCEEDED','FAILED','REFUNDED')",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_booking_reservation_status",
        "bookings",
        "reservation_status IN ('RESERVED','CONFIRMED','RELEASED')",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_booking_state_consistency",
        "bookings",
        "(status = 'PENDING') OR "
        "(status = 'CONFIRMED' AND reservation_status = 'CONFIRMED' "
        "AND payment_status = 'SUCCEEDED' AND payment_id IS NOT NULL "
        "AND confirmed_at IS NOT NULL "
        "AND jsonb_array_length(ticket_ids) > 0) OR "
        "(status = 'FAILED' AND failure_code IS NOT NULL "
        "AND failure_reason IS NOT NULL) OR "
        "(status = 'CANCELLED' AND cancellation_reason IS NOT NULL "
        "AND cancelled_at IS NOT NULL)",
        schema=SCHEMA,
    )

    for name in (
        "compensation_updated_at",
        "payment_refunded_at",
        "payment_recorded_at",
        "payment_failure_code",
        "compensation_provider_reference",
        "payment_provider_reference",
        "reservation_released_at",
        "reservation_expires_at",
        "reservation_version",
        "intended_terminal_status",
        "compensation_reason",
        "compensation_action",
        "compensation_status",
    ):
        op.drop_column("bookings", name, schema=SCHEMA)

    op.alter_column("bookings", "payment_method", nullable=False, schema=SCHEMA)
    op.alter_column("bookings", "reservation_id", nullable=False, schema=SCHEMA)
