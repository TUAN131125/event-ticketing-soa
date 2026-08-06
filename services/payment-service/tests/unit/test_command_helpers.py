"""Guards for the helpers shared by the payment command handlers."""

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from app.application.common import (
    event_payload,
    failure_event_payload,
    refund_event_payload,
)
from app.domain.entities import Payment
from app.domain.enums import RefundKind
from app.domain.rules import canonical_request_hash
from app.domain.value_objects import PaymentDraft, Refund
from app.infrastructure.database.repositories import contains_pattern

NOW = datetime.now(UTC)
EVENTS = Path(__file__).resolve().parents[2] / "contracts" / "events"


def draft() -> PaymentDraft:
    return PaymentDraft.from_request(
        booking_id="BK00000001",
        customer_id="C001",
        amount=Decimal("240.00"),
        currency="VND",
        payment_method="CARD_TOKEN",
        provider="sandbox-provider",
    )


def new_payment() -> Payment:
    return Payment.create(payment_id="PAY00000001", draft=draft(), now=NOW)


def required_payload_fields(filename: str) -> set[str]:
    schema = json.loads((EVENTS / filename).read_text(encoding="utf-8"))
    definitions = schema["$defs"]
    payload = definitions.get("payload") or definitions["paymentPayload"]
    return set(payload["required"])


def test_create_request_hash_is_unchanged_by_the_draft_refactor() -> None:
    # Idempotency records written before PaymentDraft existed must still replay,
    # so the hashed payload has to keep its exact keys and string formatting.
    legacy_payload = {
        "bookingId": "BK00000001",
        "customerId": "C001",
        "amount": "240.00",
        "currency": "VND",
        "paymentMethod": "CARD_TOKEN",
        "provider": "sandbox-provider",
    }
    assert draft().to_payload() == legacy_payload
    assert canonical_request_hash(draft().to_payload()) == canonical_request_hash(
        legacy_payload
    )


def test_failure_event_payload_matches_the_published_schema() -> None:
    payment = new_payment()
    payment.fail(
        failure_code="DECLINED",
        reason="issuer declined",
        provider_reference=None,
        expected_version=1,
        now=NOW,
    )
    payload = failure_event_payload(payment)
    assert set(payload) == required_payload_fields("payment-failed.schema.json")
    assert payload["failureCode"] == "DECLINED"
    assert payload["reason"] == "issuer declined"


def test_refund_event_payload_matches_the_published_schema() -> None:
    payment = new_payment()
    payment.authorize(provider_reference="txn-001", expected_version=1, now=NOW)
    payment.capture(provider_reference="txn-001", expected_version=2, now=NOW)
    refund: Refund = payment.refund(
        refund_id="RF000000001",
        amount=Decimal("40.00"),
        reason="seat downgrade",
        provider_reference="refund-001",
        kind=RefundKind.REQUESTED,
        expected_version=3,
        now=NOW,
    )
    payload = refund_event_payload(payment, refund)
    assert set(payload) == required_payload_fields("payment-refunded.schema.json")
    assert payload["refundAmount"] == "40.00"
    assert payload["providerRefundReference"] == "refund-001"


def test_cancellation_event_payload_matches_the_published_schema() -> None:
    payment = new_payment()
    payment.cancel(
        reason="booking abandoned",
        provider_reference=None,
        expected_version=1,
        now=NOW,
    )
    payload = {**event_payload(payment), "reason": payment.cancellation_reason}
    assert set(payload) == required_payload_fields("payment-cancelled.schema.json")


def test_search_wildcards_are_treated_as_literal_text() -> None:
    assert contains_pattern("PAY001") == "%PAY001%"
    assert contains_pattern("100%") == "%100\\%%"
    assert contains_pattern("a_b") == "%a\\_b%"
    assert contains_pattern("back\\slash") == "%back\\\\slash%"
