"""Provider THAT dang dung trong MVP: in email ra log/console thay vi
gui that. Du de demo va kiem tra noi dung, khong can cau hinh SMTP."""
from app.observability.logs import get_logger

logger = get_logger("notification.console_provider")


class ConsoleEmailProvider:
    def send(self, to: str, subject: str, body: str) -> None:
        logger.info("GUI EMAIL toi=%s | tieu de=%s | noi dung=%s", to, subject, body)
