"""Value object cho loai ve va gia."""
from dataclasses import dataclass


@dataclass(frozen=True)
class TicketType:
    type: str
    price: int

    def __post_init__(self):
        if self.price < 0:
            raise ValueError("Gia ve khong duoc am")
