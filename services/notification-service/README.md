# Notification Service

Nhan su kien nghiep vu qua 1 webhook chuan hoa (`POST /webhooks/events`,
dung `EventEnvelope`), gui email, va cho phep Admin/Ops tra cuu/gui lai/
quan ly template. Bam sat hop dong chinh thuc **Giai doan 5**
(`contracts/openapi/notification-service.yaml`, `contracts/sql/001_baseline.sql`)
va dac ta **Giai doan 3** (SVC-08, action NOT-01 -> NOT-10).

## Kien truc

```text
HTTP (FastAPI)
    |
    v
app/api/v1        - webhooks (nhan tu ESB) / deliveries (Admin,Ops) / templates (Admin)
    |
    v
app/application    - use case: receive_event, retry_delivery, upsert_template, ...
    |
    v
app/domain         - entity + rule thuan nghiep vu (InboundEvent, Delivery, Template)
    |
    v
app/repositories    - interface (Protocol)
    |
    v
app/infrastructure/database - Postgres*Repository (SQLAlchemy 2.0)
    |
    v
PostgreSQL, schema "notification": inbound_events, deliveries,
                                    delivery_attempts, templates
```

## Endpoint (khop hop dong Giai doan 5)

| Method | Path | Auth | NOT-xx |
|---|---|---|---|
| GET | `/health/live`, `/health/ready` | khong | - |
| POST | `/webhooks/events` | HMAC `X-Signature` (khong JWT) | NOT-01/02/03/04 |
| GET | `/deliveries` | Bearer JWT (role admin/ops) | - |
| GET | `/deliveries/{id}` | Bearer JWT (role admin/ops) | NOT-07 |
| POST | `/deliveries/{id}/retry` | Bearer JWT (role admin/ops) + `Idempotency-Key` | NOT-05/08 |
| PUT | `/templates/{code}` | Bearer JWT (role admin) + `Idempotency-Key` + `If-Match` (tru lan tao dau) | NOT-09 |

`eventType` duoc ho tro: `booking.confirmed`, `booking.failed`,
`event.changed`, `ticket.issued`.

Loi tra ve dung dinh dang hop dong:
`{correlationId, traceId, error:{code, message, retryable, details?}}`.

## Idempotency & fault tolerance

- **NOT-01/02**: `eventId` la PRIMARY KEY `notification.inbound_events` -
  moi eventId chi xu ly 1 lan, ke ca ESB retry webhook (tra 409
  `DUPLICATE_EVENT`).
- **NOT-05/06**: gui that bai -> `RETRY_PENDING` (exponential backoff,
  `next_attempt_at`) -> sau 5 lan -> `DEAD_LETTER`. Retry thu cong qua
  Admin/Ops (`POST /deliveries/{id}/retry`); **chua co scheduler tu
  dong** quet `RETRY_PENDING` da qua han (can worker/cron rieng, ngoai
  pham vi MVP nay - xem `app/resilience/retry.py`).
- **NOT-09**: template sua qua `If-Match`/`resource_version` (optimistic
  concurrency, giong ETag).
- `Idempotency-Key` (retry/template): hop dong bat buoc header nhung SQL
  baseline khong co bang `notification.idempotency_records` rieng nhu
  cac schema khac - hien chi validate header ton tai, chua co ledger
  luu response de replay y het (xem `app/resilience/idempotency.py`).

## Rieng tu (PII)

`notification.deliveries.destination_hash` luu **SHA-256** cua dia chi
nhan, KHONG luu plaintext. Dia chi that chi doc lai tu
`notification.inbound_events.payload` (JSONB, luu nguyen `data` cua
event) khi can gui/gui lai - xem `app/infrastructure/hashing.py`.

## Chay bang Docker Compose

```powershell
cd services\notification-service
# 1) dat file identity-public.pem vao thu muc keys/ (xem keys/README.md)
docker compose up --build
```

## Chay doc lap (khong Docker)

```powershell
pip install -r requirements-dev.txt
$env:NOTIFICATION_DATABASE_URL = "postgresql+psycopg://notification_service:notification_service@localhost:5437/notification_service"
alembic upgrade head
python -m uvicorn app.main:app --port 8007 --reload
```

## Test

```powershell
pytest tests/unit -v          # 20 test, khong can Postgres
pytest tests/integration -m integration -v   # 11 test, can Postgres
```
