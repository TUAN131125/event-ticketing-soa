"""Seat domain types."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class SeatStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    HELD = "HELD"
    SOLD = "SOLD"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True)
class SeatView:
    event_id: str
    seat_id: str
    section: str
    row_label: str
    seat_number: str
    ticket_type: str
    status: SeatStatus
    resource_version: int
