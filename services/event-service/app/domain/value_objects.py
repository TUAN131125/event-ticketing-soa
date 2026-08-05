"""Event-owned immutable value objects."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Money:
    amount_minor: int
    currency: str

    def __post_init__(self) -> None:
        if self.amount_minor < 0:
            raise ValueError("Money amountMinor cannot be negative")
        if len(self.currency) != 3 or not self.currency.isupper():
            raise ValueError("Money currency must be an uppercase ISO code")


@dataclass(frozen=True, slots=True)
class TicketType:
    code: str
    name: str
    price: Money
