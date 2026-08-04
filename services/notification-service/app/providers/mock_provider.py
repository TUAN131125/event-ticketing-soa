"""Provider danh cho unit test: khong in log, chi luu lai trong bo nho de
assert trong test (vd tests/unit). `fail_times` cho phep mo phong
PROVIDER_TEMPORARY_ERROR trong N lan gui dau tien - dung de test luong
retry/dead-letter (NOT-05/NOT-06) ma khong can provider that."""
from app.domain.exceptions import ProviderTemporaryError


class MockEmailProvider:
    def __init__(self, fail_times: int = 0) -> None:
        self.sent: list[dict] = []
        self._fail_times = fail_times
        self._calls = 0

    def send(self, to: str, subject: str, body: str) -> None:
        self._calls += 1
        if self._calls <= self._fail_times:
            raise ProviderTemporaryError("Mo phong loi provider tam thoi")
        self.sent.append({"to": to, "subject": subject, "body": body})
