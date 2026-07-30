"""Reservation domain types."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class ReservationStatus(StrEnum):
    ACTIVE = "ACTIVE"
    CONFIRMED = "CONFIRMED"
    RELEASED = "RELEASED"
    EXPIRED = "EXPIRED"


@dataclass(frozen=True, slots=True)
class ReservationView:
    reservation_id: str
    booking_id: str
    event_id: str
    seat_ids: tuple[str, ...]
    status: ReservationStatus
    expires_at: datetime
    extend_count: int
    resource_version: int
    created_at: datetime
    updated_at: datetime
