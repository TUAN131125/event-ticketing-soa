# Event Ticketing SOA

This monorepo runs the ticketing workflow behind a contract-first ESB. Runtime contracts in
`/contracts` are the only source of truth; `dist/contracts` is generated output.

## Local startup

Prerequisites: Docker Desktop/Engine with Compose v2, Python 3.12 and OpenSSL.

```sh
python contracts/scripts/validate_contracts.py
python contracts/scripts/build_contracts.py
cp .env.example .env
sh scripts/generate-local-keys.sh
docker compose --profile all up --build --wait
```

The key script is an explicit local bootstrap step. Containers never create or replace signing
keys. Edit `.env` before any shared use; `.env` and `local-secrets/*` are ignored by Git.

Migrations run only in one-shot Compose jobs (`identity-migrate` through
`orchestrator-migrate`). Application entrypoints use `app.main:create_app --factory` and start
only after their migration job succeeds.

Stop and remove local data with:

```sh
docker compose down --volumes --remove-orphans
```

## Ports and boundaries

| Component | Port |
|---|---:|
| ESB | 8000 |
| Customer | 8001 |
| Event | 8002 |
| Seat Inventory | 8003 |
| Booking | 8004 |
| Payment | 8005 |
| Ticket | 8006 |
| Notification | 8007 |
| Realtime | 8008 |
| Identity | 8009 |
| Customer Web / Admin Web | 3000 / 3001 |

Browsers call only ESB, Identity and Realtime. ESB-to-provider calls use Service JWTs;
Notification webhooks use HMAC. Liveness is `/health/live`; Compose readiness uses
`/health/ready`.

Individual provider profiles are available (`identity`, `customer`, `event`, `seat`, `booking`,
`payment`, `ticket`, `notification`, `realtime`). The `all` profile is the supported end-to-end
configuration because ESB orchestration requires every provider.
