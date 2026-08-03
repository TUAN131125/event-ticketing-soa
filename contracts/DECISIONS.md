# Official contract decisions

All decisions below are closed for the clean-slate official baseline `1.0.0`.

- **GOV-001** — Root `contracts/` is the only canonical authorable contract source.
- **GOV-002** — Official baseline is clean-slate v1.0.0; prior contract generations and a second major catalog are not maintained.
- **MAP-001** — Customer Service owns the active, auditable `identitySubject` ↔ `customerId` mapping.
- **ID-001** — Identity Service is an official v1 architecture component and does not own Customer mapping or issue authoritative `customerId`.
- **RT-AUTH-001** — Realtime browser authentication uses an ESB-issued signed, short-lived, single-use WebSocket ticket; internal status ingestion uses `InternalServiceJwt`.
- **NOTIFICATION-EVENT-001** — `notification.requested` is excluded from the v1 baseline; Notification continues to accept supported events through `POST /webhooks/events`.

Prompt 2 status: **COMPLETE**.
