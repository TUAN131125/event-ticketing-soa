"""Fixture dung chung cho integration test - can PostgreSQL that dang
chay (vi du qua `docker compose up postgres` hoac Laragon).

QUAN TRONG: fixture nay KHONG con dung chung database voi demo/thuyet
trinh nua. Truoc day dung thang CUSTOMER_DATABASE_URL nen moi lan chay
`pytest tests/integration` se TRUNCATE xoa sach du lieu demo (C001 =
Nguyen Van An bi thay bang du lieu rac cua test) - day la loi thuc te da
gap. Bay gio fixture tu suy ra 1 database RIENG bang cach them hau to
"_test" vao ten database, tu tao database do neu chua co, va tu tao bang
qua SQLAlchemy metadata (khong can chay Alembic that cho database test -
day la database dung 1 lan roi bo, khong can lich su migration).
"""
from __future__ import annotations

import re

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import ProgrammingError

from app.config import get_settings, reset_settings_cache
from app.infrastructure.database.models import Base, customer_id_seq
from app.infrastructure.database.repositories import PostgresCustomerRepository
from app.infrastructure.database.session import dispose_engine, get_engine


def _derive_test_database_url() -> str:
    base_url = get_settings().database_url
    match = re.search(r"/([A-Za-z0-9_]+)$", base_url)
    if match is None:
        raise RuntimeError(f"Khong doc duoc ten database tu URL: {base_url}")
    db_name = match.group(1)
    test_db_name = db_name if db_name.endswith("_test") else f"{db_name}_test"
    # An toan: KHONG BAO GIO cho phep test chay tren database khong co
    # hau to "_test" - day la hang rao cuoi cung chan lap lai su co xoa
    # nham du lieu demo.
    assert test_db_name.endswith("_test"), "Test database phai co hau to _test"
    return base_url[: base_url.rfind("/") + 1] + test_db_name


def _ensure_test_database_exists(test_db_url: str) -> None:
    maintenance_url = test_db_url[: test_db_url.rfind("/") + 1] + "postgres"
    maintenance_engine = create_engine(maintenance_url, isolation_level="AUTOCOMMIT")
    test_db_name = test_db_url.rsplit("/", 1)[1]
    try:
        with maintenance_engine.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{test_db_name}"'))
    except ProgrammingError:
        pass  # Database da ton tai tu lan chay truoc - binh thuong.
    finally:
        maintenance_engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def _setup_test_database():
    reset_settings_cache()
    test_db_url = _derive_test_database_url()
    _ensure_test_database_exists(test_db_url)

    import os

    os.environ["CUSTOMER_DATABASE_URL"] = test_db_url
    reset_settings_cache()
    dispose_engine()

    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS customer"))
        conn.commit()
    Base.metadata.create_all(engine)
    # customer_id_seq la Sequence doc lap (khong gan lam server_default
    # cua cot nao) nen Base.metadata.create_all() KHONG tu tao no - phai
    # tao rieng, giong nhu migration 0001 da lam thu cong bang op.execute.
    customer_id_seq.create(engine, checkfirst=True)
    yield
    dispose_engine()


@pytest.fixture
def postgres_repo(_setup_test_database):
    engine = get_engine()
    with engine.connect() as conn:
        # Xoa het du lieu, giu lai bang do fixture session-scope o tren da
        # tao - moi test bat dau tu trang thai sach, khong phu thuoc thu
        # tu chay. Day la database "_test" rieng, khong dung chung voi
        # database demo nua.
        conn.execute(text("TRUNCATE TABLE customer.customers CASCADE"))
        conn.execute(text("TRUNCATE TABLE customer.idempotency_records"))
        conn.execute(text("ALTER SEQUENCE customer.customer_id_seq RESTART WITH 1"))
        conn.commit()
    yield PostgresCustomerRepository()
