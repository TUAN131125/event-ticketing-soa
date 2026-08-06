# Booking Service — Event Ticketing SOA/ESB

Booking Service là nguồn dữ liệu có thẩm quyền cho **Booking aggregate**, lịch sử
chuyển trạng thái và bằng chứng phục hồi của quy trình đặt vé. Service không tự
kiểm tra ghế, không xử lý tiền và không phát hành vé; ESB cung cấp các bằng chứng
đã nhận từ Seat Inventory, Payment và Ticket thông qua API nội bộ.

Phiên bản hiện tại: **2.0.0**.

## Phạm vi nghiệp vụ

Implementation chỉ bao phủ các hành động đã được mô tả trong tài liệu Booking
Service và contract Giai đoạn 5:

| Mã | Hành động | Implementation |
|---|---|---|
| BKG-01 | CreateBooking | Tạo `PENDING`, lưu item và price snapshot authoritative |
| BKG-02 | GetBooking | Đọc Booking aggregate |
| BKG-03 | ListCustomerBookings | Danh sách có phân trang |
| BKG-04 | AttachReservation | Gắn reservation evidence, chuyển `SEAT_RESERVED` |
| BKG-05 | StartPayment | Chỉ chạy sau reservation, chuyển `PAYMENT_PROCESSING` |
| BKG-06 | RecordPayment | Ghi `SUCCEEDED`, `FAILED` hoặc `UNKNOWN` |
| BKG-07 | AttachTickets | Chỉ nhận ticket sau payment thành công và seat confirmed |
| BKG-08 | ConfirmBooking | Chỉ xác nhận khi đủ Seat, Payment và Ticket evidence |
| BKG-09 | FailBooking | Fail trực tiếp hoặc vào `COMPENSATION_PENDING` |
| BKG-10 | CancelBooking | Cancel theo trạng thái và bằng chứng release/refund |
| BKG-11 | Resume/Reconcile | Tìm booking treo và đề xuất bước phục hồi tiếp theo |
| BKG-12 | AuditTransition | Audit bất biến và transactional outbox |

Không có nghiệp vụ thanh toán, khóa ghế, phát hành vé hoặc gửi notification nằm
trong domain của service này.

## State machine

Các trạng thái Booking được lưu đúng contract:

```text
PENDING
  └─ AttachReservation ───────────────> SEAT_RESERVED
       └─ StartPayment ───────────────> PAYMENT_PROCESSING
            ├─ RecordPayment UNKNOWN ─> PAYMENT_PROCESSING
            ├─ RecordPayment FAILED ──> PAYMENT_PROCESSING
            ├─ RecordPayment SUCCEEDED
            │    └─ ConfirmReservation
            │         └─ AttachTickets
            │              └─ ConfirmBooking ─────────> CONFIRMED
            └─ FailBooking ───────────> FAILED hoặc COMPENSATION_PENDING

PENDING / SEAT_RESERVED / CONFIRMED
  └─ CancelBooking ──────────────────> CANCELLED hoặc COMPENSATION_PENDING

COMPENSATION_PENDING
  ├─ RecordPayment để giải quyết payment UNKNOWN
  └─ RecordCompensationResult ───────> FAILED hoặc CANCELLED
```

### Luồng thành công chuẩn

```text
CreateBooking
→ AttachReservation (RESERVED + expiresAt)
→ StartPayment
→ RecordPayment (SUCCEEDED/CAPTURED)
→ ConfirmReservationEvidence
→ AttachTickets
→ ConfirmBooking
```

`ConfirmBooking` bị từ chối nếu thiếu bất kỳ bằng chứng nào sau đây:

- reservation chưa `CONFIRMED`;
- payment chưa `SUCCEEDED` hoặc chưa có `paymentId`;
- số lượng ticket không bằng số booking item.

### Payment không xác định

`UNKNOWN` hoặc payment vẫn `PROCESSING` không bị ghi thành `FAILED`. Khi
Fail/Cancel được yêu cầu, Booking chuyển sang `COMPENSATION_PENDING` với action
`RECONCILE_PAYMENT`. Sau khi Payment Service trả kết quả authoritative, ESB ghi
kết quả qua `RecordPayment`; Booking mới xác định release/refund cần thực hiện.

### Compensation

Booking không tự suy luận rằng ghế đã release hoặc tiền đã refund. Trạng thái
terminal chỉ được ghi khi có evidence:

| Evidence hiện tại | Action còn lại |
|---|---|
| Payment `PROCESSING/UNKNOWN` | `RECONCILE_PAYMENT` |
| Reservation còn active, payment chưa thành công | `RELEASE_RESERVATION` |
| Payment thành công, không còn reservation active | `REFUND_PAYMENT` |
| Reservation active và payment thành công | `RELEASE_AND_REFUND` |
| Không còn nghĩa vụ | `NONE` |

`RecordCompensationResult` phải cung cấp evidence phù hợp trước khi Booking được
đóng thành `FAILED` hoặc `CANCELLED`.

## API

Tất cả endpoint nghiệp vụ là API nội bộ và yêu cầu:

- `X-Service-Token`
- `X-Caller-Service`
- `X-Correlation-ID` được dùng hoặc sinh bởi middleware
- `Idempotency-Key` cho command
- `If-Match` hoặc legacy `expectedVersion` cho mutation

| Method | Path | operationId | Trạng thái |
|---|---|---|---|
| POST | `/bookings` | `createBooking` | Giữ nguyên API cũ |
| GET | `/bookings` | `listBookings` | Giữ nguyên API cũ |
| GET | `/bookings/{booking_id}` | `getBooking` | Giữ nguyên API cũ |
| GET | `/customers/{customer_id}/bookings` | `listCustomerBookings` | Giữ nguyên API cũ |
| POST | `/bookings/{booking_id}/reservation` | `attachReservation` | Cũ + canonical evidence |
| POST | `/bookings/{booking_id}/payment-started` | `startPayment` | Giữ nguyên API cũ |
| POST | `/bookings/{booking_id}/payment-result` | `recordPayment` | Cũ + `paymentStatus` mới |
| POST | `/bookings/{booking_id}/tickets` | `attachTickets` | Giữ nguyên API cũ |
| POST | `/bookings/{booking_id}/confirm` | `confirmBooking` | Cũ + evidence mới |
| POST | `/bookings/{booking_id}/fail` | `failBooking` | Cũ + compensation evidence |
| POST | `/bookings/{booking_id}/cancel` | `cancelBooking` | Cũ + compensation evidence |
| GET | `/bookings/reconciliation` | `reconcileBookings` | Hoàn thiện BKG-11 |
| GET | `/bookings/{booking_id}/history` | `getBookingHistory` | Bổ sung cho BKG-12 |
| POST | `/bookings/{booking_id}/reservation-confirmed` | `confirmReservationEvidence` | Bổ sung evidence BKG-04 |
| POST | `/bookings/{booking_id}/compensation-result` | `recordCompensationResult` | Bổ sung evidence BKG-09/10 |
| GET | `/health/live` | `bookingLiveness` | Public liveness |
| GET | `/health/ready` | `bookingReadiness` | DB/schema readiness |

Contract versioned nằm tại:

```text
contracts/openapi/booking-service.yaml
contracts/events/booking-*.schema.json
```

Contract OpenAPI được sinh từ runtime bằng:

```bash
PYTHONPATH=. python scripts/export_openapi.py
```

## Optimistic concurrency và tương thích API

Response của `create`, `get` và mọi mutation trả:

```http
ETag: "4"
```

Client mới gửi:

```http
If-Match: "4"
```

Client cũ vẫn có thể gửi:

```json
{"expectedVersion": 4}
```

Nếu cả hai được gửi, hai version phải giống nhau. Nếu không có cả hai hoặc chúng
không khớp, service trả `INVALID_REQUEST`. Version stale trả
`VERSION_CONFLICT`.

### Tương thích payload cũ

Các contract cũ vẫn được giữ:

- `unitPrice` dạng số và `currency` ở cấp booking;
- `ticketType` và `ticketTypeCode`;
- `AttachReservation` cũ không có structured evidence được hiểu là reservation
  đã confirmed;
- `RecordPayment.succeeded` vẫn hoạt động;
- `FailBooking.reasonCode` vẫn được nhận;
- `expectedVersion` trong body vẫn hoạt động.

Payload mới bổ sung evidence mà không đổi operation ID hoặc path cũ.

## Idempotency và transaction

Mỗi command:

1. Chuẩn hóa payload và tính SHA-256 request hash.
2. Khóa advisory lock theo operation và `Idempotency-Key`.
3. Replay cùng key + cùng payload bằng response đã lưu.
4. Trả `IDEMPOTENCY_KEY_REUSED` nếu cùng key nhưng payload khác.
5. Khóa row Booking bằng `FOR UPDATE`.
6. Cập nhật aggregate, audit, outbox và idempotency record trong cùng transaction.

Reservation ID được khóa riêng và có unique constraint để không thể gắn cùng
reservation cho hai booking.

## Khả năng chịu lỗi

- Bounded retry chỉ cho PostgreSQL serialization/deadlock (`40001`, `40P01`).
- Lock timeout và statement timeout cấu hình theo environment.
- Connection pool có `pool_pre_ping` và timeout hữu hạn.
- Liveness không phụ thuộc database.
- Readiness chỉ `READY` khi DB và toàn bộ bảng/migration cần thiết tồn tại.
- Graceful draining làm readiness trả 503 trong shutdown.
- Payment `UNKNOWN` không bị chuyển thành thất bại giả.
- Compensation có trạng thái `PENDING`, `FAILED`, `COMPLETED` và evidence rõ.
- Audit và outbox commit cùng state transition.
- Database constraints bảo vệ các invariant `PENDING`, `SEAT_RESERVED`,
  `PAYMENT_PROCESSING`, `CONFIRMED`, `FAILED`, `CANCELLED` và
  `COMPENSATION_PENDING`.

## Error contract

Lỗi được chuẩn hóa dạng:

```json
{
  "correlationId": "...",
  "error": {
    "code": "VERSION_CONFLICT",
    "message": "Booking resource version does not match",
    "retryable": false,
    "details": {
      "expectedVersion": 3,
      "actualVersion": 4
    }
  }
}
```

Các mã nghiệp vụ chính:

- `INVALID_REQUEST`
- `BOOKING_NOT_FOUND`
- `INVALID_BOOKING_STATE`
- `VERSION_CONFLICT`
- `IDEMPOTENCY_KEY_REUSED`
- `RESERVATION_CONFLICT`
- `MISSING_RESERVATION_EVIDENCE`
- `MISSING_PAYMENT_EVIDENCE`
- `MISSING_TICKET_EVIDENCE`
- `COMPENSATION_EVIDENCE_REQUIRED`
- `DEPENDENCY_UNAVAILABLE`

## Database và migration

Booking sở hữu schema PostgreSQL `booking`. Không có foreign key xuyên service.

```bash
export BOOKING_DATABASE_URL='postgresql+psycopg://booking:booking@localhost:5437/booking'
alembic upgrade head
```

Các migration refactor:

- `0003_booking_state_machine_refactor.py`
- `0004_booking_active_state_constraints.py`

Không xóa migration cũ. Migration mới mở rộng schema để giữ tương thích dữ liệu
hiện có.

## Chạy local

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8004
```

Hoặc:

```bash
docker compose up --build --wait
```

## Kiểm thử

Unit, contract và security:

```bash
pytest -q
```

PostgreSQL integration/concurrency:

```bash
export BOOKING_TEST_DATABASE_URL='postgresql+psycopg://booking:booking@localhost:5437/booking_test'
pytest -q -m 'integration or concurrency'
```

Contract reproducibility:

```bash
PYTHONPATH=. python scripts/export_openapi.py
pytest -q tests/contract
```

## Cấu hình chính

| Biến | Mặc định local |
|---|---|
| `BOOKING_APP_ENV` | `local` |
| `BOOKING_DATABASE_URL` | PostgreSQL tại `localhost:5437/booking` |
| `BOOKING_SERVICE_TOKEN` | `local-development-token` |
| `BOOKING_DB_POOL_SIZE` | `10` |
| `BOOKING_DB_MAX_OVERFLOW` | `20` |
| `BOOKING_DB_POOL_TIMEOUT_SECONDS` | `5` |
| `BOOKING_DB_CONNECT_TIMEOUT_SECONDS` | `3` |
| `BOOKING_DB_LOCK_TIMEOUT_MS` | `2000` |
| `BOOKING_DB_STATEMENT_TIMEOUT_MS` | `10000` |
| `BOOKING_IDEMPOTENCY_TTL_SECONDS` | `86400` |
| `BOOKING_LOG_LEVEL` | `INFO` |
| `BOOKING_DOCS_ENABLED` | Bật ngoài production |

Ở production, `BOOKING_SERVICE_TOKEN` phải là giá trị riêng có ít nhất 32 ký tự.
