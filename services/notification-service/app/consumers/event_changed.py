"""Xu ly su kien thay doi lich (EVT-12) - chua co endpoint webhook goi
toi trong MVP (Event Service chua publish event nay), giu lai lam diem
mo rong khi nhom trien khai day du."""
from app.providers.email_provider import EmailProvider


def handle_event_changed(payload: dict, provider: EmailProvider) -> str:
    with open("app/templates/event_changed.html", encoding="utf-8") as f:
        body = f.read().format(
            event_id=payload.get("eventId", ""),
            change_summary=payload.get("changeSummary", ""),
        )
    provider.send(to=payload.get("customerEmail", "unknown"),
                   subject="Su kien thay doi", body=body)
    return "SENT"
