"""Fixture dung chung cho integration test - can PostgreSQL that dang
chay. Doc NOTIFICATION_DATABASE_URL tu bien moi truong.

QUAN TRONG (bai hoc tu 1 bug thuc te da xay ra): don dep DU LIEU va
SEQUENCE ca TRUOC lan yield lan SAU khi test ket thuc (finally), khong
chi truoc nhu ban cu - de khong bao gio de lai du lieu/anh huong sequence
sau khi chay het bo test, tranh gay nham lan/loi khi nguoi dung test tay
qua webhook that ngay sau khi chay `pytest tests/integration`."""
from __future__ import annotations

import pytest
from sqlalchemy import text

from app.application.services.template_defaults import DEFAULT_TEMPLATES
from app.config import reset_settings_cache
from app.infrastructure.database.repositories import (
    PostgresEventDeliveryRepository,
    PostgresTemplateRepository,
)
from app.infrastructure.database.session import dispose_engine, get_engine

_TABLES = (
    "notification.delivery_attempts",
    "notification.deliveries",
    "notification.inbound_events",
)


def _reset(engine) -> None:
    with engine.connect() as conn:
        conn.execute(text(f"TRUNCATE TABLE {', '.join(_TABLES)}"))
        conn.execute(text("ALTER SEQUENCE notification.delivery_id_seq RESTART WITH 1"))
        # templates duoc migration hat giong san. Xoa template test tu
        # tao (khac 4 ma mac dinh) VA khoi phuc lai NOI DUNG + version=1
        # cho 4 ma mac dinh - vi test co the sua chinh cac ma nay (vd
        # test_template_save_updates_existing_row), khong chi tao them.
        conn.execute(
            text(
                "DELETE FROM notification.templates WHERE template_code NOT IN "
                "('booking_confirmed','booking_failed','event_changed','ticket_issued')"
            )
        )
        for code, (subject, body) in DEFAULT_TEMPLATES.items():
            conn.execute(
                text(
                    "UPDATE notification.templates SET subject = :subject, body = :body, "
                    "resource_version = 1, updated_at = now() WHERE template_code = :code"
                ),
                {"subject": subject, "body": body, "code": code},
            )
        conn.commit()


@pytest.fixture
def postgres_repo():
    reset_settings_cache()
    dispose_engine()
    engine = get_engine()
    _reset(engine)
    try:
        yield PostgresEventDeliveryRepository()
    finally:
        _reset(engine)
        dispose_engine()


@pytest.fixture
def postgres_template_repo():
    reset_settings_cache()
    dispose_engine()
    engine = get_engine()
    _reset(engine)
    try:
        yield PostgresTemplateRepository()
    finally:
        _reset(engine)
        dispose_engine()
