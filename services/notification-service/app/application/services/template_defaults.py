"""Noi dung template mac dinh - dung de (1) hat giong bang
notification.templates trong migration 0002, va (2) lam fallback khi
render() ma DB chua co dong tuong ung (vi du moi tao schema, chua chay
seed). Nguon su that lau dai la bang DB (PUT /templates/{code} - NOT-09);
day chi la gia tri khoi tao."""
from __future__ import annotations

DEFAULT_TEMPLATES: dict[str, tuple[str, str]] = {
    "booking_confirmed": (
        "Dat ve thanh cong",
        "<h2>Dat ve thanh cong!</h2>\n"
        "<p>Xin chao {customer_name},</p>\n"
        "<p>Booking <strong>{booking_id}</strong> cua ban da duoc xac nhan.</p>\n"
        "<p>Ma ve: {ticket_ids}</p>\n",
    ),
    "booking_failed": (
        "Dat ve khong thanh cong",
        "<h2>Dat ve khong thanh cong</h2>\n"
        "<p>Booking <strong>{booking_id}</strong> khong the hoan tat.</p>\n"
        "<p>Ly do: {reason}</p>\n",
    ),
    "event_changed": (
        "Su kien thay doi",
        "<h2>Su kien thay doi</h2>\n"
        "<p>Su kien <strong>{event_id}</strong> vua duoc cap nhat.</p>\n"
        "<p>Chi tiet: {change_summary}</p>\n",
    ),
    "ticket_issued": (
        "Ve dien tu da duoc phat hanh",
        "<h2>Ve dien tu da duoc phat hanh</h2>\n"
        "<p>Ve <strong>{ticket_id}</strong> cho su kien <strong>{event_id}</strong> da san sang.</p>\n"
        "<p>Vui long kiem tra ung dung/email de xem ma QR check-in.</p>\n",
    ),
}

# EventType.value -> template_code (Muc 2 dac ta: moi eventType ung voi 1
# template mac dinh).
EVENT_TYPE_TEMPLATE_CODE: dict[str, str] = {
    "booking.confirmed": "booking_confirmed",
    "booking.failed": "booking_failed",
    "event.changed": "event_changed",
    "ticket.issued": "ticket_issued",
}
