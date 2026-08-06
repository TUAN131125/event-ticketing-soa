# Payment Service

Payment Service sở hữu vòng đời thanh toán giả lập của hệ thống đặt vé. Service
không nhận hoặc lưu PAN, CVV, ngày hết hạn hay thông tin thẻ thô. Mọi số tiền
được lưu bằng `Decimal/Numeric`, mọi command tài chính được bảo vệ bằng
idempotency, transaction và state guard.

Bản refactor này triển khai các hành động PAY-01 đến PAY-10 trong tài liệu Giai
đoạn 3, đồng thời giữ nguyên các API cũ và bổ sung các API canonical còn thiếu.

## Nghiệp vụ được hỗ trợ

| Mã | Hành động | Implementation |
|---|---|---|
| PAY-01 | CreatePayment | Tạo một payment `PENDING` cho booking; kiểm tra amount/currency với booking evidence khi được yêu cầu |
| PAY-02 | AuthorizePayment | Mô phỏng success/decline/timeout hoặc ghi nhận provider outcome đã xác minh |
| PAY-03 | CapturePayment | Chỉ capture sau authorize; timeout chuyển `UNKNOWN`, không tự kết luận thất bại |
| PAY-04 | GetPayment | Đọc trạng thái authoritative và `resourceVersion` |
| PAY-05 | CancelPayment | Chỉ hủy trước capture |
| PAY-06 | RefundPayment | Full/partial refund; tổng refund không vượt captured amount |
| PAY-07 | HandleProviderCallback | HMAC, replay window, body-size guard, dedup `eventId`, immutable provider-event ledger |
| PAY-08 | ReconcilePayment | Giải quyết `UNKNOWN`; worker retry theo bounded exponential backoff |
| PAY-09 | IdempotencyReplay | Cùng key/cùng payload trả snapshot cũ; cùng key/khác payload trả `IDEMPOTENCY_KEY_REUSED` |
| PAY-10 | AuditLedger | Audit, refund ledger, provider-event ledger và transactional outbox |

## State machine

```text
PENDING ──authorize──> AUTHORIZED ──capture──> CAPTURED
   │                       │                      │
   ├──decline────────────> FAILED                ├──refund một phần──> PARTIALLY_REFUNDED
   ├──cancel─────────────> CANCELLED             └──refund đủ───────> REFUNDED
   └──provider timeout───> UNKNOWN ──reconcile──> trạng thái cuối phù hợp
```

`UNKNOWN` luôn lưu:

- `lastStableStatus`;
- `pendingOperation`;
- `unknownSince`;
- `reconciliationStatus`, số lần thử và thời điểm thử tiếp theo.

Worker không retry command tài chính mù. Nó chỉ đọc outcome provider đã được lưu
hoặc chờ callback/reconciliation evidence; nếu chưa có kết quả, payment tiếp tục
ở `UNKNOWN` và lần thử sau được hoãn bằng backoff có giới hạn.

## API và tương thích ngược

Mọi endpoint nội bộ yêu cầu `X-Service-Token` và `X-Caller-Service`. Command yêu
cầu `Idempotency-Key`. Mutation hỗ trợ cả `expectedVersion` cũ và header
`If-Match` mới; nếu cung cấp đồng thời, hai giá trị phải khớp.

| Method | Endpoint | operationId | Ghi chú |
|---|---|---|---|
| `POST` | `/payments` | `createPayment` | Giữ payload cũ; bổ sung `methodToken`, `bookingEvidence` |
| `GET` | `/payments` | `listPayments` | Giữ nguyên |
| `GET` | `/payments/{paymentId}` | `getPayment` | Giữ nguyên |
| `GET` | `/payments/{paymentId}/refunds` | `listPaymentRefunds` | Giữ nguyên query cũ |
| `POST` | `/payments/{paymentId}/authorize` | `authorizePayment` | Giữ `approved`; bổ sung `providerStatus` |
| `POST` | `/payments/{paymentId}/capture` | `capturePayment` | Giữ `succeeded`; bổ sung `providerStatus` |
| `POST` | `/payments/{paymentId}/cancel` | `cancelPayment` | Giữ nguyên, bổ sung provider outcome optional |
| `POST` | `/payments/{paymentId}/refund` | `refundPayment` | Legacy path được giữ nguyên |
| `POST` | `/payments/{paymentId}/refunds` | `createPaymentRefund` | Canonical path bổ sung |
| `POST` | `/payments/provider-callback` | `handleProviderCallback` | PAY-07 bổ sung |
| `POST` | `/payments/{paymentId}/reconcile` | `reconcilePayment` | PAY-08 hoàn thiện |
| `GET` | `/payments/{paymentId}/provider-events` | `listPaymentProviderEvents` | Bằng chứng callback/reconciliation |

Contract máy đọc nằm tại
`contracts/openapi/payment-service.yaml`. File này được sinh trực tiếp từ FastAPI
và contract test yêu cầu nội dung static/runtime bằng nhau.

### Tương thích payload

- `AuthorizePayment`: client cũ dùng `approved`; client mới dùng
  `providerStatus=AUTHORIZED|FAILED|UNKNOWN`.
- `CapturePayment`: client cũ dùng `succeeded`; client mới dùng
  `providerStatus=CAPTURED|FAILED|UNKNOWN`.
- `RefundPayment`: client cũ dùng `amount`; client mới có thể dùng
  `amountMinor`. Hai field cùng xuất hiện phải biểu diễn cùng một giá trị.
- Callback chấp nhận header canonical `X-Webhook-Timestamp` /
  `X-Webhook-Signature` và alias cũ `X-Provider-Timestamp` /
  `X-Provider-Signature`. Hai alias xung đột bị từ chối.

Để không phá client cũ, decline qua boolean cũ vẫn trả Payment `FAILED` như trước.
Payload canonical mới trả lỗi `402 PAYMENT_DECLINED`. Outcome không xác định trả
`202` cùng Payment `UNKNOWN`.

## Booking evidence và toàn vẹn số tiền

`CreatePayment` có thể nhận `bookingEvidence` gồm booking ID, amount, currency,
resource version và evidence ID. Service xác minh số tiền/currency trước khi tạo
payment và trả `409 PAYMENT_AMOUNT_MISMATCH` khi không khớp.

- Local mặc định cho phép thiếu evidence để giữ tương thích với client cũ.
- Ngoài local, `PAYMENT_REQUIRE_BOOKING_EVIDENCE` mặc định là `true`.
- Không có dữ liệu nào do browser gửi được xem là authoritative nếu chưa qua
  ESB/Booking Service.

## Provider callback

Callback ký HMAC-SHA256 trên:

```text
<timestamp>.<raw request body>
```

Yêu cầu:

- timestamp nằm trong replay window;
- signature dùng constant-time comparison;
- body không vượt giới hạn cấu hình;
- `eventId` là khóa dedup;
- cùng `eventId` và cùng payload trả kết quả cũ;
- cùng `eventId` nhưng payload khác trả conflict;
- amount/currency callback, nếu có, phải khớp payment;
- operation và provider status phải tạo thành một outcome hợp lệ.

Provider event, payment mutation, audit, outbox và idempotency snapshot được commit
trong cùng transaction.

## Khả năng chịu lỗi

- PostgreSQL row lock và advisory lock chống concurrent duplicate.
- Unique constraint bảo đảm một payment cho mỗi booking.
- Unique provider reference/refund reference chống gắn một giao dịch provider cho
  nhiều aggregate.
- Optimistic concurrency bằng `resourceVersion`/`If-Match`.
- DB lock timeout, statement timeout và retry ngắn cho lỗi persistence transient.
- Provider timeout không được map thành `FAILED`; payment chuyển `UNKNOWN`.
- Reconciliation worker dùng bounded exponential backoff và giới hạn số lần thử.
- Callback lặp/out-of-order không được làm state regression.
- Transactional outbox có relay riêng, delivery at-least-once và dead-letter
  evidence khi vượt `PAYMENT_OUTBOX_MAX_ATTEMPTS`.
- Structured error envelope luôn có `correlationId` và không trả traceback/secret.

## Worker

### Reconciliation worker

```powershell
python -m app.workers.reconciliation_worker
```

Worker lấy các payment `UNKNOWN` đã đến hạn bằng batch query, sau đó gọi
`ReconcilePayment` bằng idempotency key ổn định theo payment/version. Callback có
thể giải quyết payment song song; version/state conflict khi đó được xem là an
toàn và worker bỏ qua candidate cũ.

### Outbox relay

```powershell
python -m app.workers.outbox_relay
```

Relay lấy event bằng `SELECT ... FOR UPDATE SKIP LOCKED`, publish rồi mới đánh dấu
`published_at`. Consumer phải dedup theo `eventId` vì delivery là at-least-once.
Khi `PAYMENT_OUTBOX_WEBHOOK_URL` để trống, relay ghi envelope ra log để phục vụ
local/demo.

## Chạy local

```powershell
Copy-Item .env.example .env
docker compose up --build
```

- API: `http://localhost:8005`
- PostgreSQL: `localhost:5438`
- API container chạy migration trước khi nhận traffic.
- Compose chạy riêng API, reconciliation worker và outbox relay.

Chạy ngoài container:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
$env:PAYMENT_DATABASE_URL='postgresql+psycopg://payment:payment@localhost:5438/payment'
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\uvicorn.exe app.main:app --port 8005
```

## Kiểm thử và contract

```powershell
python -m pytest
python -m compileall -q app tests migrations scripts
python scripts/export_openapi.py
alembic upgrade head --sql
```

Integration/concurrency test cần PostgreSQL thật:

```powershell
docker compose -f docker-compose.test.yml up -d
$env:PAYMENT_TEST_DATABASE_URL='postgresql+psycopg://payment:payment@localhost:55435/payment_test'
python -m pytest
```

Quality gate khi dependency dev đã được cài:

```powershell
python -m ruff format --check app tests
python -m ruff check app tests
python -m mypy app
```

## Production checklist

- Dùng secret riêng tối thiểu 32 ký tự cho `PAYMENT_SERVICE_TOKEN` và
  `PAYMENT_PROVIDER_CALLBACK_SECRET`; placeholder local bị từ chối ngoài local.
- Bật `PAYMENT_REQUIRE_BOOKING_EVIDENCE=true`.
- Tắt docs nếu không cần bằng `PAYMENT_DOCS_ENABLED=false`.
- Chạy API, reconciliation worker và outbox relay thành process/container riêng.
- Dùng TLS/mTLS/private network cho traffic nội bộ.
- Cấu hình webhook ingress, secret manager và consumer dedup `eventId`.
- Cảnh báo theo payment `UNKNOWN`, reconciliation backlog/exhausted, callback
  signature invalid, idempotency conflict, provider timeout và outbox backlog.
- Không sửa ledger trực tiếp bằng SQL; mọi correction đi qua callback/reconcile và
  được audit.
