#!/usr/bin/env python3
"""Restricted-environment verification for the Frontend <-> ESB public contract."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

import yaml

FRONTEND_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = FRONTEND_ROOT.parent / "contracts" / "esb-public-api.yaml"
GENERATED_PATH = FRONTEND_ROOT / "shared-ui/src/generated/esb-public-api.ts"
GENERATED_CONTRACTS = (
    (FRONTEND_ROOT.parent / "contracts/esb-public-api.yaml", FRONTEND_ROOT / "shared-ui/src/generated/esb-public-api.ts"),
    (FRONTEND_ROOT.parent / "contracts/providers/identity-service.yaml", FRONTEND_ROOT / "shared-ui/src/generated/identity-service.ts"),
    (FRONTEND_ROOT.parent / "contracts/providers/realtime-status-service.yaml", FRONTEND_ROOT / "shared-ui/src/generated/realtime-service.ts"),
    (FRONTEND_ROOT.parent / "contracts/providers/realtime-status.asyncapi.yaml", FRONTEND_ROOT / "shared-ui/src/generated/realtime-messages.ts"),
)
ALIASES_PATH = FRONTEND_ROOT / "shared-ui/src/frontend-esb-contract.ts"
ADMIN_SOURCE = FRONTEND_ROOT / "admin-web/src"

EXPECTED = {
    ("post", "/api/auth/register"): "registerIdentityAccountViaEsb",
    ("post", "/api/auth/login"): "loginIdentityAccountViaEsb",
    ("post", "/api/auth/refresh"): "refreshIdentitySessionViaEsb",
    ("post", "/api/auth/logout"): "logoutIdentitySessionViaEsb",
    ("get", "/api/auth/me"): "getCurrentIdentityPrincipalViaEsb",
    ("get", "/api/events"): "publicListEvents",
    ("get", "/api/events/{eventId}"): "publicGetEvent",
    ("get", "/api/events/{eventId}/seat-map"): "publicGetEventSeatMap",
    ("post", "/api/bookings"): "placeBooking",
    ("get", "/api/bookings"): "publicListBookings",
    ("get", "/api/bookings/{bookingId}"): "publicGetBooking",
    ("post", "/api/bookings/{bookingId}/cancel"): "publicCancelBooking",
    ("get", "/api/tickets"): "publicListTickets",
    ("get", "/api/tickets/{ticketId}"): "publicGetTicket",
    ("get", "/api/me/customer"): "getMyCustomerProfile",
    ("put", "/api/me/customer"): "upsertMyCustomerProfile",
    ("post", "/api/admin/events"): "adminCreateEvent",
    ("put", "/api/admin/events/{eventId}"): "adminReplaceEvent",
    ("post", "/api/admin/events/{eventId}/publish"): "adminPublishEvent",
    ("post", "/api/admin/events/{eventId}/pause"): "adminPauseEvent",
    ("post", "/api/admin/events/{eventId}/close"): "adminCloseEvent",
    ("post", "/api/admin/events/{eventId}/cancel"): "adminCancelEvent",
    ("get", "/api/admin/events/{eventId}/seat-inventory"): "adminGetSeatInventory",
    ("put", "/api/admin/events/{eventId}/seat-inventory"): "adminConfigureSeatInventory",
    ("post", "/api/check-in/validate"): "validateTicketForCheckIn",
    ("post", "/api/check-in/tickets/{ticketId}"): "checkInTicketViaEsb",
    ("post", "/api/realtime/ws-tickets"): "issueRealtimeWebSocketTicket",
    ("get", "/api/traces/{correlationId}"): "getWorkflowTrace",
    ("get", "/api/health"): "aggregateHealth",
}


def main() -> None:
    raw = CONTRACT_PATH.read_bytes()
    document = yaml.safe_load(raw)
    for (method, path), operation_id in EXPECTED.items():
        operation = document.get("paths", {}).get(path, {}).get(method)
        if not operation or operation.get("operationId") != operation_id:
            raise SystemExit(f"Contract mismatch: {method.upper()} {path} -> {operation_id}")

    schemes = document.get("components", {}).get("securitySchemes", {})
    if schemes.get("UserJwt", {}).get("scheme") != "bearer":
        raise SystemExit("ESB OpenAPI is missing UserJwt")
    for method, path in (("get", "/api/auth/me"), ("post", "/api/bookings"), ("get", "/api/tickets"), ("post", "/api/check-in/validate")):
        security = document["paths"][path][method].get("security", [])
        if not any("UserJwt" in entry for entry in security):
            raise SystemExit(f"Missing UserJwt: {method.upper()} {path}")
    for path in ("/api/auth/refresh", "/api/auth/logout"):
        security = document["paths"][path]["post"].get("security", [])
        if not any(
            "RefreshCookie" in entry and "CsrfCookie" in entry and "CsrfHeader" in entry
            for entry in security
        ):
            raise SystemExit(f"Missing refresh-cookie/CSRF security: POST {path}")

    generated = GENERATED_PATH.read_text(encoding="utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    for contract_path, generated_path in GENERATED_CONTRACTS:
        contract_digest = hashlib.sha256(contract_path.read_bytes()).hexdigest()
        output = generated_path.read_text(encoding="utf-8")
        if f"// Contract SHA-256: {contract_digest}" not in output:
            raise SystemExit(f"Generated TypeScript is stale: {generated_path}")
    for marker in ("export interface paths", "export interface operations", "export interface components"):
        if marker not in generated:
            raise SystemExit(f"Generated ESB types missing {marker}")
    if re.search(r"export type (paths|operations) = Record<string, never>", generated):
        raise SystemExit("Placeholder ESB operation/path types are forbidden")

    aliases = ALIASES_PATH.read_text(encoding="utf-8")
    if "operations['" not in aliases:
        raise SystemExit("Frontend wire aliases must derive from generated operation contracts")

    admin_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in ADMIN_SOURCE.rglob("*.ts*")
        if path.is_file()
    )
    if "'/bookings'" in admin_text or 'path="/bookings"' in admin_text:
        raise SystemExit("Undocumented admin booking UI remains connected to owner-scoped APIs")
    admin_client = (ADMIN_SOURCE / "api/esb.ts").read_text(encoding="utf-8")
    if "if (!ifMatch)" not in admin_client:
        raise SystemExit("Admin check-in client does not fail closed without If-Match")
    if "export type { AggregateHealth, PublicEvent }" not in admin_client:
        raise SystemExit("Admin ESB client does not re-export page contract types")

    auth_files = [
        FRONTEND_ROOT / "customer-web/src/api/auth-client.ts",
        FRONTEND_ROOT / "admin-web/src/api/auth.ts",
        FRONTEND_ROOT / "customer-web/.env.example",
        FRONTEND_ROOT / "admin-web/.env.example",
        FRONTEND_ROOT / "customer-web/Dockerfile",
        FRONTEND_ROOT / "admin-web/Dockerfile",
        FRONTEND_ROOT / "customer-web/vite.config.ts",
        FRONTEND_ROOT / "customer-web/README.md",
        FRONTEND_ROOT / "admin-web/README.md",
        FRONTEND_ROOT / "README.md",
    ]
    for path in auth_files:
        text = path.read_text(encoding="utf-8")
        if "VITE_IDENTITY_API_URL" in text or "localhost:8009" in text:
            raise SystemExit(f"Frontend still calls Identity directly: {path}")
    for path in auth_files[:2]:
        if "/api/auth/" not in path.read_text(encoding="utf-8"):
            raise SystemExit(f"Auth client does not use the ESB facade: {path}")
    build_inputs = "\n".join(path.read_text(encoding="utf-8") for path in auth_files[2:])
    if "VITE_REALTIME_WS_URL" in build_inputs or "localhost:8008" in build_inputs:
        raise SystemExit("Frontend still permits direct Realtime configuration")

    compose = yaml.safe_load((FRONTEND_ROOT.parent / "compose.yaml").read_text(encoding="utf-8"))
    for service in ("customer-web", "admin-web"):
        args = compose["services"][service]["build"]["args"]
        if set(args) != {"VITE_ESB_API_URL"}:
            raise SystemExit(f"{service} Compose build exposes non-ESB browser URLs: {set(args)}")

    customer_client = (FRONTEND_ROOT / "customer-web/src/api/esb-client.ts").read_text(
        encoding="utf-8"
    )
    if "export type { PlaceBookingRequest, RealtimeWsTicket }" not in customer_client:
        raise SystemExit("Customer ESB client does not re-export hook/WebSocket contract types")

    print(
        f"Verified {len(EXPECTED)} frontend operations, generated type hash {digest}, "
        "and admin scope/If-Match constraints."
    )


if __name__ == "__main__":
    main()
