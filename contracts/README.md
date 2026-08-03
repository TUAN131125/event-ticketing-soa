# Event Ticketing SOA contracts

## Canonical source

`contracts/` is the only authorable contract source for the system. The catalog is the official clean-slate baseline `1.0.0`; previously published shapes are not maintained here. Service-local artifacts must be generated from this root and must never be independently authored.

## Structure

- `manifest.yaml`: canonical artifact inventory, semantic owner, publication version and SHA-256 digest.
- `DECISIONS.md`: closed architecture and governance decisions.
- `common/`: shared ErrorResponse, event envelope, Money, pagination and security schemes.
- `openapi/`: REST contracts owned by Customer, Event, Booking, Payment, Ticket, Notification, Realtime, Identity and ESB.
- `soap/`: Seat Inventory WSDL/XSD and SOAP examples.
- `events/`: producer-owned event schemas.
- `webhooks/`: Notification webhook schema.
- `websocket/`: Realtime protocol, frames and close-code registry.
- `examples/`: validated HTTP, event, webhook and WebSocket examples.
- `scripts/`: offline validation and deterministic catalog maintenance.

## Semantic ownership

- Identity owns accounts, credentials, roles, refresh sessions and JWKS, but not Customer mapping.
- Customer owns `identitySubject` ↔ `customerId` mapping and customer lifecycle.
- Booking owns booking state and resource access decisions.
- ESB owns the public orchestration boundary and signed Realtime ticket issuance.
- Realtime owns ephemeral connections, subscription protocol and best-effort status projection only.
- Event, Payment, Ticket, Notification and Seat Inventory own their respective domain interfaces and messages.
- Architecture owns the common technical schemas and security-scheme names.

## Interface classes

- `public`: browser, operator or external integration surface.
- `business`: provider-owned domain operation in the official baseline.
- `internal`: service-to-service operation protected by `InternalServiceJwt` or an explicitly declared internal mechanism.
- `operational`: implementation health or metrics endpoint; excluded from integration operation counts unless explicitly cataloged.

## Validation

From repository root:

```bash
python contracts/scripts/refresh_manifest.py
python contracts/scripts/validate_contracts.py
python contracts/scripts/check_manifest.py
python contracts/scripts/check_placeholders.py
```

Validation uses OpenAPI 3.1, JSON Schema Draft 2020-12 with a canonical `$id` registry, SOAP/XSD compilation, examples, semantic security assertions, cleanup rules and manifest digests.

## Changing a contract

1. Change only the root artifact owned by the provider or common architecture owner.
2. Preserve `version: 1.0.0` and `contractStatus: canonical-v1` until a separately authorized baseline decision exists.
3. Update examples and deterministic generators together with the contract.
4. Refresh the manifest and run all validators.
5. Generate service-local artifacts from root; do not hand-edit generated copies.

From this baseline onward, removing an operation or response, adding a required request field/header, narrowing a type or enum, changing security requirements, changing event required fields/schemaVersion, or changing SOAP namespaces/actions/faults is breaking. Behavioral compatibility additionally requires provider and consumer contract tests.

Prompt 3 will freeze this official v1 baseline and prepare the ESB implementation boundary.
