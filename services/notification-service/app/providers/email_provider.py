"""Interface (Protocol) cho noi gui thong bao that su - de de thay the
console/mock bang SMTP/SES that sau nay."""
from typing import Protocol


class EmailProvider(Protocol):
    def send(self, to: str, subject: str, body: str) -> None: ...
