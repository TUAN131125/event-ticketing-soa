# Báo cáo refactor Payment Service

## 1. Phạm vi

Bản refactor được thực hiện trên `payment-service.zip` và đối chiếu trực tiếp với
`05_PAYMENT_SERVICE.docx` cùng contract Giai đoạn 5. Phạm vi chỉ gồm các nghiệp
vụ PAY-01 đến PAY-10 đã được tài liệu nêu; không bổ sung payment thật, PAN/CVV,
PCI-DSS, nhiều provider production hoặc nghiệp vụ ngoài tài liệu.

## 2. Kết quả theo Action Catalog

| Mã | Kết quả | Implementation chính |
|---|---|---|
| PAY-01 CreatePayment | Hoàn thiện | Một payment cho mỗi booking; `Decimal/Numeric`; booking evidence; `PAYMENT_AMOUNT_MISMATCH`; idempotency |
| PAY-02 AuthorizePayment | Hoàn thiện | Legacy `approved`; canonical `providerStatus`; mock success/decline/timeout; 402 cho canonical decline |
| PAY-03 CapturePayment | Hoàn thiện | Authorize-before-capture; provider reference guard; timeout → `UNKNOWN`/202 |
| PAY-04 GetPayment | Giữ nguyên và mở rộng | Trả authoritative state, ETag/resourceVersion và reconciliation evidence |
| PAY-05 CancelPayment | Hoàn thiện | Chỉ trước capture, state/version/idempotency guard |
| PAY-06 RefundPayment | Hoàn thiện | Partial/full refund, refund ledger, tổng refund ≤ captured amount, legacy/new path |
| PAY-07 HandleProviderCallback | Bổ sung đầy đủ | HMAC, replay window, body limit, header aliases, `eventId` dedup, immutable provider-event ledger |
| PAY-08 ReconcilePayment | Refactor đầy đủ | `UNKNOWN`, final provider evidence, bounded exponential backoff, max attempts, worker riêng |
| PAY-09 IdempotencyReplay | Giữ và chuẩn hóa | Cùng payload replay; khác payload trả `IDEMPOTENCY_KEY_REUSED`; advisory lock |
| PAY-10 AuditLedger | Mở rộng | Payment audit, refund ledger, provider-event ledger và transactional outbox |

## 3. Những thay đổi quan trọng

### 3.1 Domain và state machine

- Bổ sung `PaymentStatus.UNKNOWN`.
- Lưu `lastStableStatus`, `pendingOperation`, `unknownSince`,
  `reconciliationStatus`, `reconciliationAttempts`, `reconciliationDueAt`,
  `lastReconciledAt` và lỗi đối soát.
- Không map timeout thành `FAILED`.
- Chặn state regression, callback sai operation/status và provider reference mâu
  thuẫn.
- Khi reconciliation đạt số lần thử tối đa, `reconciliationDueAt` được đặt `NULL`
  để worker không quay vòng vô hạn.

### 3.2 Provider callback

- Endpoint mới: `POST /payments/provider-callback`.
- Hỗ trợ header canonical `X-Webhook-Timestamp`/`X-Webhook-Signature` và alias cũ
  `X-Provider-Timestamp`/`X-Provider-Signature`.
- Chữ ký HMAC-SHA256 trên `timestamp.rawBody`, so sánh constant-time.
- Chống replay theo timestamp và giới hạn kích thước body.
- Dedupe theo `eventId`; cùng ID/khác payload trả conflict.
- Callback, provider event, payment mutation, audit, outbox và idempotency được
  commit trong cùng transaction.

### 3.3 Reconciliation và fault tolerance

- `ReconcilePayment` đọc final provider evidence, bỏ qua marker `UNKNOWN` cục bộ.
- Nếu outcome chưa có, service ghi evidence thất bại trước rồi mới trả 503.
- Backoff tăng theo cấp số nhân, có trần, batch size và poll interval cấu hình.
- Worker `app.workers.reconciliation_worker` chạy độc lập với API.
- Worker dùng idempotency key ổn định theo payment/version và chịu được callback
  giải quyết payment đồng thời.
- Docker Compose đã bổ sung reconciliation worker và giữ outbox relay riêng.

### 3.4 Toàn vẹn số tiền

- `CreatePayment` hỗ trợ `bookingEvidence` authoritative.
- Kiểm tra booking ID, customer ID, amount và currency trước khi tạo payment.
- Local giữ khả năng tương thích khi thiếu evidence; môi trường ngoài local mặc
  định yêu cầu evidence.
- Callback có amount/currency thì bắt buộc khớp aggregate.

### 3.5 Contract và tương thích ngược

Đã giữ nguyên toàn bộ 11 operation cũ:

- `paymentLiveness`, `paymentReadiness`;
- `createPayment`, `listPayments`, `getPayment`, `listPaymentRefunds`;
- `authorizePayment`, `capturePayment`, `cancelPayment`, `refundPayment`,
  `reconcilePayment`.

Đã bổ sung ba operation:

- `handleProviderCallback`;
- `createPaymentRefund` tại canonical path `/payments/{paymentId}/refunds`;
- `listPaymentProviderEvents`.

Các field cũ `amount`, `paymentMethod`, `approved`, `succeeded`, `expectedVersion`
và legacy refund path vẫn được chấp nhận. Các field/header mới là additive.
Contract test kiểm tra operation ID cũ và các request field cũ không bị xóa.

## 4. Cấu trúc refactor

- `app/domain`: aggregate, enum, value object và business rules.
- `app/application/commands`: một module cho từng command.
- `app/application/provider_outcomes.py`: normalization, validation và apply outcome
  dùng chung cho command/callback/reconcile.
- `app/application/provider_events.py`: immutable provider-event ledger helper.
- `app/infrastructure/providers/mock.py`: provider giả lập deterministic cho demo
  success/decline/timeout.
- `app/workers/reconciliation_worker.py`: PAY-08 worker.
- `app/workers/outbox_relay.py`: event relay at-least-once.
- `contracts/openapi`: contract FastAPI đã đồng bộ.
- `contracts/events`: schema cho created/authorized/succeeded/failed/cancelled/
  refunded/unknown/reconciled.
- `migrations/versions/0002_payment_dependability.py`: migration additive.

## 5. Kết quả kiểm tra

### Đã chạy thành công

```text
pytest -q
46 passed, 9 skipped
```

Chín test bị skip là integration/concurrency PostgreSQL vì môi trường thực thi
không có `PAYMENT_TEST_DATABASE_URL` và không có Docker.

```text
pytest --cov=app --cov-report=term -q
46 passed, 9 skipped
Total coverage: 66%
```

```text
python -m compileall -q app tests migrations scripts
PASS
```

```text
python scripts/export_openapi.py
Runtime OpenAPI == static OpenAPI: PASS
11/11 operation cũ được giữ nguyên
14 operation tổng cộng
```

```text
alembic upgrade head --sql
PASS: 0001 -> 0002 sinh SQL PostgreSQL hợp lệ
```

```text
Parse docker-compose.yml, docker-compose.test.yml và OpenAPI YAML
PASS
```

Kiểm tra line length theo cấu hình Ruff 88 ký tự cho `app/tests/scripts`:
`PASS`.

### Chưa chạy được trong môi trường hiện tại

- PostgreSQL integration/concurrency runtime: `NOT_RUN` vì không có Docker và
  không có database test được cấp.
- Ruff và Mypy chính thức: `NOT_RUN` vì executable/package không có trong runtime
  hiện tại. `requirements-dev.txt` vẫn pin phiên bản để CI/local chạy các gate này.

Không tuyên bố PostgreSQL integration, concurrency, Ruff hoặc Mypy là PASS khi
chưa có bằng chứng thực thi.

## 6. Hướng chạy nghiệm thu đầy đủ

```powershell
docker compose -f docker-compose.test.yml up -d
$env:PAYMENT_TEST_DATABASE_URL='postgresql+psycopg://payment:payment@localhost:55435/payment_test'
python -m pytest
python -m ruff format --check app tests
python -m ruff check app tests
python -m mypy app
```

Khi tích hợp full stack, bật:

```text
PAYMENT_REQUIRE_BOOKING_EVIDENCE=true
```

và chạy riêng ba process/container: API, reconciliation worker, outbox relay.
