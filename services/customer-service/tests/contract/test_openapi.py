from pathlib import Path

from libs.contract_testing import assert_openapi_conformance, make_service_jwt_settings

from app.config import Settings
from app.main import create_app


def test_provider_matches_canonical_contract() -> None:
    settings = Settings(
        app_env="test",
        log_level="WARNING",
        service_name="customer-service",
        database_url="postgresql+psycopg://customer:test@localhost/customer",
        db_pool_size=1,
        db_max_overflow=0,
        sql_echo=False,
        service_jwt=make_service_jwt_settings("customer-service"),
    )
    canonical = Path(__file__).parents[4] / "contracts" / "customer-service.yaml"
    assert_openapi_conformance(create_app(settings).openapi(), canonical)
