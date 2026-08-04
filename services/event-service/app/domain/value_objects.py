"""Value object cho tien te va loai ve - khop schema Money/ticketTypes
trong OpenAPI (amountMinor + currency, khong con la so nguyen gia don
gian nhu ban truoc)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Money:
    amount_minor: int
    currency: str = "VND"

    def __post_init__(self):
        if self.amount_minor < 0:
            raise ValueError("amountMinor khong duoc am")
        if len(self.currency) != 3 or not self.currency.isupper():
            raise ValueError("currency phai la ma 3 chu in hoa, vi du VND")


@dataclass(frozen=True)
class TicketType:
    code: str
    name: str
    price: Money
