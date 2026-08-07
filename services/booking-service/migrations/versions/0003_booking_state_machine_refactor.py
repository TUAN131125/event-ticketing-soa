"""Expand Booking state machine and compensation evidence.

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-06

Compatibility note
------------------
Revision 0002 was rewritten (commit 8b53f0f) after some databases had already applied its
earlier edition. Those databases are stamped 0002 but lack what the current 0002 adds, so
this revision's first ALTERs used to fail on them with
``column "reservation_status" ... does not exist``. Because 0003 is where the failure
surfaced and no database had yet applied 0003 or 0004, the compatibility preamble below
lives here rather than in a later repair revision, which could never have been reached.

The preamble is additive and idempotent: on a database created by the current 0002 it does
nothing at all, and on an older one it creates exactly what the current 0002 would have. It
never drops or rewrites data.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "booking"

# What the current revision 0002 adds relative to its earlier edition. Measured by diffing a
# database built from the current 0002 against a database that applied the earlier one.
LEGACY_0002_COLUMNS: tuple[tuple[str, sa.Column], ...] = (
    (
        "reservation_status",
        sa.Column(
            "reservation_status",
            sa.String(20),
            nullable=False,
            server_default="RESERVED",
        ),
    ),
    (
        "reservation_confirmed_at",
        sa.Column("reservation_confirmed_at", sa.DateTime(timezone=True)),
    ),
    ("tickets_attached_at", sa.Column("tickets_attached_at", sa.DateTime(timezone=True))),
)


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _booking_columns() -> dict[str, dict]:
    return {
        column["name"]: column
        for column in _inspector().get_columns("bookings", schema=SCHEMA)
    }


def _check_constraint_names(table: str) -> set[str]:
    return {
        constraint["name"]
        for constraint in _inspector().get_check_constraints(table, schema=SCHEMA)
    }


def _drop_check_constraints_if_present(names: Sequence[str]) -> None:
    """Drop only the v1 checks a given database actually has.

    Which of these exist depends on which edition of 0002 ran, so an unconditional drop
    fails on the older schema. This is not masking a wrong schema: every name here is
    recreated in its v2 form further down, and any that is absent is one the older 0002
    never created.
    """
    present = _check_constraint_names("bookings")
    for name in names:
        if name in present:
            op.drop_constraint(name, "bookings", schema=SCHEMA, type_="check")


LEGACY_FAILURE_REASON = "Migrated from v1: original failure reason was not recorded"

# Booking v1 stored the *Payment* service's vocabulary in payment_status. Booking v2 has its
# own enumeration, so legacy values are translated with the same mapping the orchestrator
# uses (contracts/payment-service.yaml -> contracts/booking-service.yaml).
LEGACY_PAYMENT_STATUS: dict[str, str] = {
    "CAPTURED": "SUCCEEDED",
    "AUTHORIZED": "PROCESSING",
    "CANCELLED": "FAILED",
    "PARTIALLY_REFUNDED": "REFUND_PENDING",
}
V2_PAYMENT_STATUSES = (
    "PENDING",
    "PROCESSING",
    "SUCCEEDED",
    "FAILED",
    "UNKNOWN",
    "REFUND_PENDING",
    "REFUNDED",
)


def _backfill_legacy_v1_rows() -> None:
    """Translate v1 rows into the v2 vocabulary using only evidence already stored.

    Nothing is promoted to a better outcome than the row already recorded: a payment is
    only called SUCCEEDED where v1 had already captured it, and a booking is never moved
    into CONFIRMED or SUCCEEDED without its own evidence columns saying so.

    Runs after the v1 checks are dropped and before the v2 checks are created. On a database
    built by the current 0002 there are no v1 rows, so every statement matches nothing.
    """
    bind = op.get_bind()

    # 1. payment_status: Payment vocabulary -> Booking vocabulary.
    for legacy, v2 in LEGACY_PAYMENT_STATUS.items():
        bind.execute(
            sa.text(
                "UPDATE booking.bookings SET payment_status = :v2 "
                "WHERE payment_status = :legacy"
            ),
            {"v2": v2, "legacy": legacy},
        )

    # 2. A booking mid-payment must not still read PENDING; it holds a payment_id, so
    #    PROCESSING is what that evidence supports. It is deliberately not SUCCEEDED.
    bind.execute(
        sa.text(
            "UPDATE booking.bookings SET payment_status = 'PROCESSING' "
            "WHERE status = 'PAYMENT_PROCESSING' AND payment_id IS NOT NULL "
            "AND payment_status = 'PENDING'"
        )
    )

    # 3. A CONFIRMED booking's reservation is confirmed by definition; v1 had no column to
    #    say so. Only rows that already carry a reservation_id are touched.
    bind.execute(
        sa.text(
            "UPDATE booking.bookings SET reservation_status = 'CONFIRMED' "
            "WHERE status = 'CONFIRMED' AND reservation_id IS NOT NULL"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE booking.bookings SET reservation_status = 'RELEASED' "
            "WHERE status = 'CANCELLED' AND reservation_id IS NOT NULL"
        )
    )

    # 4. v2 requires a failure reason next to a failure code. v1 never stored one, so the
    #    row is marked as such rather than given an invented reason.
    bind.execute(
        sa.text(
            "UPDATE booking.bookings SET failure_reason = :reason "
            "WHERE status = 'FAILED' AND failure_reason IS NULL"
        ),
        {"reason": LEGACY_FAILURE_REASON},
    )

    # Fail loudly rather than let a constraint creation produce an opaque error.
    leftover = bind.execute(
        sa.text(
            "SELECT payment_status, count(*) FROM booking.bookings "
            "WHERE payment_status <> ALL(:allowed) GROUP BY payment_status"
        ),
        {"allowed": list(V2_PAYMENT_STATUSES)},
    ).all()
    if leftover:
        raise RuntimeError(
            "Booking rows still hold payment_status values outside the v2 enumeration: "
            + ", ".join(f"{value}={count}" for value, count in leftover)
        )


def _apply_legacy_0002_compatibility() -> None:
    """Bring a pre-refactor 0002 database up to what the current 0002 produces."""
    existing = _booking_columns()

    for name, column in LEGACY_0002_COLUMNS:
        if name not in existing:
            op.add_column("bookings", column, schema=SCHEMA)

    # reservation_status is NOT NULL with a server default, so existing rows are filled by
    # PostgreSQL as the column is added. 'RESERVED' matches what the current 0002 gives a
    # freshly created row, and the state-machine backfill further down immediately
    # re-derives it from real evidence: rows with no reservation_id become 'PENDING'.
    # Nothing is inferred as paid or confirmed.
    if "reservation_status" not in existing:
        remaining = op.get_bind().execute(
            sa.text(
                "SELECT count(*) FROM booking.bookings WHERE reservation_status IS NULL"
            )
        ).scalar_one()
        if remaining:
            raise RuntimeError(
                f"{remaining} booking rows still have a NULL reservation_status after "
                "backfill; refusing to continue."
            )


def upgrade() -> None:
    # Databases that applied the earlier edition of 0002 are brought up to the current 0002
    # first; on an up-to-date database this is a no-op.
    _apply_legacy_0002_compatibility()

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
    _drop_check_constraints_if_present(
        (
            "ck_booking_state_consistency",
            "ck_booking_status",
            "ck_booking_payment_status",
            "ck_booking_reservation_status",
        )
    )

    # Legacy rows speak the v1 vocabulary; translate before the v2 checks exist.
    _backfill_legacy_v1_rows()

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
