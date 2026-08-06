from __future__ import annotations

import json
import time
from types import SimpleNamespace

import pytest

from app.api.router import update_my_customer_consent, upsert_my_customer
from app.api.schemas import ConsentUpdateRequest, CustomerProfileInput
from app.domain.errors import EsbError
from app.domain.models import Principal


class Auth:
    async def verify(self, authorization):
        assert authorization == "Bearer customer-token"
        return Principal("identity-1", frozenset({"CUSTOMER"}))


class NewCustomerProvider:
    def __init__(self):
        self.link_call = None

    async def resolve_identity(self, subject, ctx):
        raise EsbError("IDENTITY_NOT_MAPPED", "not mapped", 404)

    async def create(self, payload, key, ctx):
        assert payload["email"] == "customer@example.com"
        return {
            "customerId": "customer-1",
            "name": "Customer One",
            "email": "customer@example.com",
            "phone": "+84901234567",
            "status": "ACTIVE",
            "resourceVersion": 3,
            "createdAt": "2026-08-06T12:00:00Z",
            "updatedAt": "2026-08-06T12:00:00Z",
        }

    async def link_identity(self, customer_id, subject, key, if_match, ctx):
        self.link_call = (customer_id, subject, key, if_match)
        return {"customerId": customer_id, "identitySubject": subject}


class ConsentCustomerProvider:
    def __init__(self):
        self.updated = False

    async def resolve_identity(self, subject, ctx):
        return {"customerId": "customer-1"}

    async def get(self, customer_id, ctx):
        version = 8 if self.updated else 7
        return {
            "customerId": customer_id,
            "name": "Customer One",
            "email": "customer@example.com",
            "phone": None,
            "status": "ACTIVE",
            "resourceVersion": version,
            "createdAt": "2026-08-06T12:00:00Z",
            "updatedAt": "2026-08-06T12:00:00Z",
        }

    async def update_consent(self, customer_id, payload, key, if_match, ctx):
        assert if_match == '"7"'
        self.updated = True
        return {}


def fake_request(customer):
    return SimpleNamespace(
        headers={"Authorization": "Bearer customer-token"},
        state=SimpleNamespace(
            correlation_id="corr-customer",
            trace_id="a" * 32,
            deadline=time.monotonic() + 10,
        ),
        app=SimpleNamespace(state=SimpleNamespace(container=SimpleNamespace(auth=Auth(), customer=customer))),
    )


@pytest.mark.asyncio
async def test_customer_onboarding_links_identity_with_provider_precondition():
    customer = NewCustomerProvider()
    response = await upsert_my_customer(
        CustomerProfileInput(
            fullName="Customer One",
            email="customer@example.com",
            phone="+84901234567",
        ),
        fake_request(customer),
        "customer-onboard-123",
        None,
    )
    payload = json.loads(response.body)
    assert response.status_code == 201
    assert payload["customerId"] == "customer-1"
    assert response.headers["etag"] == '"3"'
    assert customer.link_call == (
        "customer-1",
        "identity-1",
        "customer-onboard-123:identity-link",
        '"3"',
    )


@pytest.mark.asyncio
async def test_consent_response_reloads_authoritative_customer_version():
    customer = ConsentCustomerProvider()
    response = await update_my_customer_consent(
        ConsentUpdateRequest(channel="EMAIL", granted=True),
        fake_request(customer),
        "consent-update-123",
        None,
    )
    payload = json.loads(response.body)
    assert payload["resourceVersion"] == 8
    assert response.headers["etag"] == '"8"'
