"""Ticket aggregate enumerations."""

from enum import StrEnum


class TicketStatus(StrEnum):
    VALID = "VALID"
    CHECKED_IN = "CHECKED_IN"
    CANCELLED = "CANCELLED"


class TicketEventType(StrEnum):
    ISSUED = "ticket.issued"
    CHECKED_IN = "ticket.checked-in"
    CANCELLED = "ticket.cancelled"
    QR_REGENERATED = "ticket.qr-regenerated"
