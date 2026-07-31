"""Provider danh cho unit test: khong in log, chi luu lai trong bo nho de
assert trong test (vd tests/unit)."""


class MockEmailProvider:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    def send(self, to: str, subject: str, body: str) -> None:
        self.sent.append({"to": to, "subject": subject, "body": body})
