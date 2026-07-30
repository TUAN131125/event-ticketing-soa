from __future__ import annotations

import pytest

from app.domain.exceptions import InvalidRequest
from app.domain.rules import (
    advisory_lock_id,
    canonical_request_hash,
    normalize_seat_ids,
    validate_hold_seconds,
)


def test_seat_ids_are_unique_and_sorted_for_lock_order() -> None:
    assert normalize_seat_ids(("B-02", "A-01")) == ("A-01", "B-02")


def test_duplicate_seat_ids_are_rejected() -> None:
    with pytest.raises(InvalidRequest):
        normalize_seat_ids(("A-01", "A-01"))


def test_hold_duration_is_bounded() -> None:
    assert validate_hold_seconds(60, 30, 900) == 60
    with pytest.raises(InvalidRequest):
        validate_hold_seconds(901, 30, 900)


def test_request_hash_is_order_independent_for_mapping_keys() -> None:
    assert canonical_request_hash({"a": 1, "b": 2}) == canonical_request_hash(
        {"b": 2, "a": 1}
    )


def test_advisory_lock_id_is_stable_and_scoped() -> None:
    assert advisory_lock_id("ReserveSeats", "key") == advisory_lock_id(
        "ReserveSeats", "key"
    )
    assert advisory_lock_id("ReserveSeats", "key") != advisory_lock_id(
        "ConfirmSeats", "key"
    )
