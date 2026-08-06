# Changelog

## 2.0.0 — 2026-08-06

### Refactor

- Tách state transition pipeline dùng chung cho mọi command.
- Chuẩn hóa Booking aggregate thành state machine đầy đủ.
- Tách transport compatibility khỏi domain command.
- Hợp nhất idempotency, row lock, audit và outbox trong một transaction pipeline.
- Lazy initialize database-backed service sau authentication.

### Added

- `SEAT_RESERVED`, `PAYMENT_PROCESSING`, `COMPENSATION_PENDING`.
- Payment evidence `UNKNOWN`, `REFUND_PENDING`, `REFUNDED`.
- Reservation evidence và compensation action/status.
- `confirmReservationEvidence`.
- `recordCompensationResult`.
- `getBookingHistory`.
- `If-Match`/`ETag` đồng thời giữ `expectedVersion` cũ.
- Reconciliation recommendation theo evidence authoritative.
- Migration `0003` và `0004`.
- JSON Schema cho bốn event Booking được tài liệu định nghĩa.
- Unit, contract, security và PostgreSQL integration/concurrency test mới.

### Fixed

- Không cho start payment trước reservation.
- Không cho attach tickets trước payment success và seat confirmation.
- Không ghi đè payment authoritative thành FAILED khi Booking fail.
- Không tự đánh dấu reservation released hoặc payment refunded.
- Không đóng Booking terminal khi compensation chưa có evidence.
- Không coi payment timeout/unknown là payment failure.
- Phân biệt payment failed với payment chưa bắt đầu trong reconciliation.
- Chống hai Booking gắn cùng một reservation.

### Compatibility

- Giữ nguyên path và operation ID cũ.
- Giữ legacy request aliases và `expectedVersion` trong body.
- Mọi thay đổi API mới là additive.
