from pathlib import Path

from libs.contract_testing import assert_openapi_conformance

from app.config import Settings
from app.main import create_app


def test_provider_matches_canonical_contract(notification_settings: Settings) -> None:
    canonical = Path(__file__).parents[4] / "contracts" / "notification-service.yaml"
    assert_openapi_conformance(create_app(notification_settings).openapi(), canonical)
