# Notification Service

Notification Service gui email khi co su kien nghiep vu tu ESB (dat ve
thanh cong/khong thanh cong), qua webhook `POST /webhooks/...`. Day la
service T2 (theo phan loai DOC-04 cua nhom): khong co tai nguyen tranh
chap dong thoi nhu Seat Inventory, nen service uu tien su don gian, ro
rang cua REST + PostgreSQL thay vi cac co che khoa nang cao.

## Kien truc

Clean Architecture / layered, cung phong cach voi cac service khac trong
repo (Customer Service, Event Service):

```text
HTTP (FastAPI)
    |
    v
app/api              - webhook (nhan tu ESB) + GET /deliveries (tra cuu)
    |
    v
app/application       - use case (handle_booking_confirmed/failed, ...)
    |
    v
app/domain            - entity + rule thuan nghiep vu, khong biet FastAPI/DB
    |
    v
app/repositories       - interface (Protocol) DeliveryRepository
    |
    v
app/infrastructure/database - PostgresDeliveryRepository (SQLAlchemy 2.0)
    |
    v
PostgreSQL (schema "notification")
```

Domain va application layer chi phu thuoc vao `DeliveryRepository`
(Protocol) va `EmailProvider` (Protocol) - khong biet du lieu luu o dau
hay email gui that su nhu the nao. `ConsoleEmailProvider` (in email ra
log, dang dung trong MVP) co the thay bang SMTP/SES that ma khong sua gi
o tang application/domain.

## Diem khac voi ban MVP truoc day

- **Idempotency**: truoc day dung 1 `set` trong bo nho (mat khi restart).
  Gio dedup theo `correlationId` duoc ep bang UNIQUE constraint that tren
  cot `notification.deliveries.correlation_id`, ben vung qua lan restart.
- **Delivery log**: truoc day dict trong bo nho. Gio la bang PostgreSQL
  that (`notification.deliveries`), van xem lai qua `GET /deliveries`.
- Hanh vi webhook khong doi: luon tra HTTP 200 kem `{"status": "SENT"}`
  hoac `{"status": "DUPLICATE_IGNORED"}`, khong bao gio tra 4xx/5xx cho
  truong hop trung lap (dung hop dong webhook idempotent voi ESB).

## Chay doc lap (khong Docker)

```powershell
cd services\notification-service
pip install -r requirements-dev.txt
$env:NOTIFICATION_DATABASE_URL = "postgresql+psycopg://notification_service:notification_service@localhost:5436/notification_service"
alembic upgrade head
python -m uvicorn app.main:app --port 8007 --reload
```

## Chay bang Docker Compose (bao gom Postgres)

```powershell
cd services\notification-service
docker compose up --build
```

## Test

```powershell
pytest tests/unit -v
pytest tests/integration -m integration -v   # can Postgres dang chay
```

## Webhook

- `POST /webhooks/booking-confirmed` - payload: `event, correlationId,
  bookingId, customerEmail, ticketIds[]`
- `POST /webhooks/booking-failed` - payload: `event, correlationId,
  bookingId, customerEmail, reason`
- `GET /deliveries` - lich su gui thong bao, moi lan gui 1 ban ghi
