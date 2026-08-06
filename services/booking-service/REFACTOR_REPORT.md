# Báo cáo refactor Booking Service 2.0.0

Ngày kiểm tra: 06/08/2026

## 1. Nguồn đối chiếu

Refactor được giới hạn theo đúng nội dung Booking Service trong:

- Giai đoạn 3 — `04_BOOKING_SERVICE.docx`;
- Giai đoạn 5 — dữ liệu, API contract, state machine, idempotency và error;
- API và operation ID đã tồn tại trong ZIP Booking Service người dùng cung cấp.

Không bổ sung nghiệp vụ ngoài BKG-01 đến BKG-12. Ba endpoint mới chỉ ghi
bằng chứng cho các nghiệp vụ đã có:

- `confirmReservationEvidence`: evidence của BKG-04;
- `recordCompensationResult`: evidence bù trừ của BKG-09/BKG-10;
- `getBookingHistory`: đọc audit của BKG-12.

## 2. Kết quả theo Action Catalog

| Mã | Kết quả sau refactor | Bảo vệ chính |
|---|---|---|
| BKG-01 CreateBooking | Hoàn thành | Price snapshot, total validation, idempotency |
| BKG-02 GetBooking | Hoàn thành | Authoritative aggregate, `ETag` |
| BKG-03 ListCustomerBookings | Hoàn thành | Phân trang, ownership reference |
| BKG-04 AttachReservation | Hoàn thành | `SEAT_RESERVED`, expiry/version, reservation uniqueness |
| BKG-05 StartPayment | Hoàn thành | Chỉ sau reservation evidence |
| BKG-06 RecordPayment | Hoàn thành | `SUCCEEDED/FAILED/UNKNOWN`, không ghi thất bại giả |
| BKG-07 AttachTickets | Hoàn thành | Chỉ sau payment success và seat confirmed |
| BKG-08 ConfirmBooking | Hoàn thành | Đủ seat/payment/ticket evidence |
| BKG-09 FailBooking | Hoàn thành | Terminal hoặc `COMPENSATION_PENDING` |
| BKG-10 CancelBooking | Hoàn thành | Release/refund evidence, không tự suy luận |
| BKG-11 Resume/Reconcile | Hoàn thành | Action theo trạng thái/evidence authoritative |
| BKG-12 AuditTransition | Hoàn thành | Immutable audit + transactional outbox |

## 3. Các lỗi nghiệp vụ đã sửa

### 3.1. Thứ tự workflow

State machine hiện enforce:

```text
PENDING
→ SEAT_RESERVED
→ PAYMENT_PROCESSING
→ payment SUCCEEDED
→ reservation CONFIRMED
→ tickets attached
→ CONFIRMED
```

Không còn cho phép:

- start payment trước reservation;
- attach ticket trước payment success;
- attach ticket khi seat chưa confirmed;
- confirm khi thiếu evidence.

### 3.2. Fail và cancel

- Không ghi đè Payment Service evidence thành `FAILED` khi Booking thất bại.
- Không tự đánh dấu ghế đã release.
- Không tự đánh dấu payment đã refund.
- Booking chỉ terminal khi nghĩa vụ compensation đã hoàn thành.
- Payment `PROCESSING/UNKNOWN` chuyển sang action `RECONCILE_PAYMENT`.
- Hỗ trợ compensation một phần và retry evidence idempotent.

### 3.3. Reconciliation

Recommendation đã phân biệt:

- chưa có reservation;
- có reservation nhưng chưa bắt đầu payment;
- payment đang processing/unknown;
- payment failed cần release và fail;
- payment succeeded cần confirm seat;
- seat confirmed cần issue tickets;
- đủ evidence cần confirm booking;
- compensation đang chờ cần hoàn tất compensation.

## 4. Refactor kiến trúc code

- Domain aggregate độc lập persistence.
- Một `BookingTransition` pipeline dùng chung cho mutation.
- Command chỉ khai báo payload, replay detection, mutation, audit và outbox.
- Transport compatibility được tách vào request schema và HTTP helper.
- Booking facade chỉ điều phối use case và bounded DB retry.
- Repository chịu row lock, advisory lock, audit, outbox và idempotency.
- Response mapping tách khỏi entity.
- Health/lifecycle tách liveness và readiness.

## 5. Khả năng chịu lỗi

- Idempotency key + canonical SHA-256 request hash.
- Replay cùng payload trả lại cùng aggregate snapshot.
- Cùng key khác payload trả `IDEMPOTENCY_KEY_REUSED`.
- `SELECT ... FOR UPDATE` cho aggregate mutation.
- PostgreSQL advisory lock cho idempotency và reservation ownership.
- Unique constraint bảo vệ một reservation chỉ thuộc một Booking.
- Retry hữu hạn cho serialization failure và deadlock.
- Lock timeout, statement timeout, pool timeout và connect timeout.
- Audit, outbox, aggregate và idempotency record commit cùng transaction.
- DB constraints bảo vệ intermediate và terminal state evidence.
- Payment unknown được reconcile, không retry mù hoặc fail đóng sai.

## 6. Contract và tương thích

### Giữ nguyên

- Toàn bộ path cũ.
- Toàn bộ operation ID cũ.
- `expectedVersion` trong body.
- `succeeded` trong RecordPayment.
- `reasonCode` trong FailBooking.
- Numeric `unitPrice` + booking currency.
- `ticketType` và `ticketTypeCode`.
- Legacy AttachReservation semantics.

### Bổ sung không breaking

- `If-Match` cho mutation.
- `ETag` trên create/get/mutation response.
- Payment `UNKNOWN/PENDING_RECONCILIATION` evidence.
- Reservation expiry/version/confirmation evidence.
- Compensation status/action/evidence.
- History, reconciliation và compensation-result APIs.

Static OpenAPI được sinh trực tiếp từ runtime và contract test yêu cầu hai bản
phải giống hoàn toàn.

## 7. Migration

- `0003`: mở rộng state machine và compensation evidence.
- `0004`: thêm DB constraints cho `PENDING`, `SEAT_RESERVED` và
  `PAYMENT_PROCESSING`.
- Legacy `PENDING` rows được chuyển sang `SEAT_RESERVED` hoặc
  `PAYMENT_PROCESSING` dựa trên evidence đã tồn tại; migration không tạo giả
  payment/seat/ticket outcome.
- Offline SQL của `alembic upgrade head --sql` đã sinh thành công qua revision
  `0004`.

## 8. Kết quả kiểm thử trong môi trường hiện tại

```text
56 passed
9 skipped
coverage: 74%
```

Chín test bị skip là PostgreSQL integration/concurrency vì môi trường thực thi
không có Docker/PostgreSQL và không đặt `BOOKING_TEST_DATABASE_URL`.

Đã thực hiện thêm:

- `python -m compileall`: PASS;
- OpenAPI runtime/static equality: PASS;
- Draft 2020-12 event schema validation: PASS;
- offline Alembic SQL generation: PASS;
- targeted mypy cho domain, schema, API, DB model/mapper: PASS;
- kiểm tra dòng Python vượt 88 ký tự: không còn.

Full-project mypy không hoàn tất trong giới hạn thời gian của môi trường; Ruff
không có executable Linux sẵn trong phiên làm việc. Không tuyên bố hai gate này
đã chạy đầy đủ.

## 9. Điều kiện xác nhận runtime cuối cùng

Trước khi merge/deploy, cần chạy trên PostgreSQL 16 thật:

```bash
export BOOKING_TEST_DATABASE_URL='postgresql+psycopg://booking:booking@localhost:5437/booking_test'
pytest -q -m 'integration or concurrency'
```

Sau đó chạy gate chuẩn:

```bash
ruff check app tests scripts migrations
mypy app
pytest -q
```

Chỉ đánh dấu PostgreSQL transaction/concurrency PASS sau khi các lệnh trên có
bằng chứng runtime.
