# ESB / BOOKING ORCHESTRATOR — DANH SÁCH LỖI, PHẦN THIẾU VÀ KẾ HOẠCH CẬP NHẬT

**Vị trí đề xuất trong repository:**

```text
gateway/booking-orchestrator/ESB_UPDATE_GAP_AND_REFACTOR_PLAN.md
```

**Ngày rà soát:** 06/08/2026  
**Phạm vi rà soát:** nhánh `main` của repository `event-ticketing-soa`, tài liệu Giai đoạn 3–5, Booking Service đã refactor, Payment Service đã refactor và frontend UI-01…UI-12 đã chuẩn bị.

---

## 1. Mục đích của tài liệu

Tài liệu này dùng làm checklist thực hiện đợt cập nhật lớn cho ESB. Mục tiêu là:

1. Sửa các lỗi orchestration hiện có.
2. Đưa các business rule đang đặt sai trong ESB về đúng service sở hữu.
3. Đồng bộ ESB với Booking Service và Payment Service mới.
4. Bổ sung các façade còn thiếu để frontend hoàn thành UI-01…UI-12.
5. Hoàn thiện reliability, security, observability và contract compatibility.
6. Không tự bổ sung nghiệp vụ ngoài tài liệu.

Tài liệu này **không phải contract mới**. Mọi path, payload và state mới chỉ được triển khai sau khi cập nhật contract canonical trong `contracts/` và contract validation pass.

---

## 2. Nguồn dùng để đối chiếu

### Tài liệu nghiệp vụ và kiến trúc

- `GIAI_DOAN_3_BO_TAI_LIEU_CHI_TIET_CAC_SERVICE/07_ESB_BOOKING_ORCHESTRATOR.docx`
- `GIAI_DOAN_3_BO_TAI_LIEU_CHI_TIET_CAC_SERVICE/09_FRONTEND_WEB_UI.docx`
- `GIAI_DOAN_4_DEPENDABILITY_KHA_NANG_CHIU_LOI_HE_THONG_DAT_VE_SOA.docx`
- `GIAI_DOAN_5_DU_LIEU_VA_API_CONTRACT_HE_THONG_DAT_VE_SOA.docx`

### Source ESB hiện tại

- `gateway/booking-orchestrator/app/application/booking.py`
- `gateway/booking-orchestrator/app/application/cancellation.py`
- `gateway/booking-orchestrator/app/application/queries.py`
- `gateway/booking-orchestrator/app/api/router.py`
- `gateway/booking-orchestrator/app/api/http.py`
- `gateway/booking-orchestrator/app/domain/models.py`
- `gateway/booking-orchestrator/app/ports/providers.py`
- `gateway/booking-orchestrator/app/adapters/rest/providers.py`
- `gateway/booking-orchestrator/app/adapters/soap/seat.py`
- `gateway/booking-orchestrator/app/workers/outbox.py`
- `gateway/booking-orchestrator/app/workers/reconciliation.py`
- `gateway/booking-orchestrator/app/main.py`
- `contracts/esb-public-api.yaml`

### Contract service đích

- Booking Service mới: `contracts/openapi/booking-service.yaml`, version `2.0.0`
- Payment Service mới: `contracts/openapi/payment-service.yaml`
- `contracts/event-service.yaml`
- `contracts/seat-inventory.wsdl`
- `contracts/seat-inventory.xsd`
- `contracts/ticket-service.yaml`

---

## 3. Ranh giới bắt buộc của ESB

Theo đặc tả ESB, ESB được phép sở hữu:

- Routing và service discovery.
- Message transformation.
- REST ↔ SOAP protocol mediation.
- Orchestration và Saga workflow.
- Timeout budget, retry policy, circuit breaker và bulkhead.
- Idempotency của public workflow.
- Workflow evidence, trace và outbox của chính ESB.
- Error normalization.
- Authentication ở ingress và kiểm tra role cho public façade.
- Publish event bất đồng bộ.

ESB **không được sở hữu**:

- Quy tắc lựa chọn loại vé.
- Bảng giá hoặc quy tắc tính giá.
- Quy tắc khóa, xác nhận hoặc giải phóng ghế.
- TTL mặc định của Seat Inventory.
- State machine Booking.
- State machine Payment hoặc kết luận kết quả payment.
- Điều kiện hợp lệ của Ticket/QR/check-in.
- State machine Event.
- Chính sách hủy/refund không được contract khóa.
- Dữ liệu domain authoritative của service khác.
- Truy cập trực tiếp database của service khác.

Quy tắc đánh giá:

> ESB có thể quyết định **gọi bước nào tiếp theo** dựa trên kết quả authoritative, nhưng không được tự tạo ra kết quả authoritative hoặc tự thay thế business rule của service.

---

# PHẦN A — LỖI PHẢI SỬA TRƯỚC

## P0-01 — Sai thứ tự ConfirmSeats và IssueTickets

### Source hiện tại

```text
gateway/booking-orchestrator/app/application/booking.py
BookingSaga._issue_and_confirm()
```

### Luồng hiện tại

```text
Payment CAPTURED
→ Ticket Service: IssueTickets
→ Booking Service: AttachTickets
→ Seat Service: ConfirmSeats
→ Booking Service: ConfirmBooking
```

### Vì sao sai

- Ticket được phát hành trước khi Seat Inventory xác nhận reservation thành `CONFIRMED`.
- Nếu ConfirmSeats thất bại, Ticket đã tồn tại dù ghế chưa được xác nhận.
- Booking Service mới chỉ cho AttachTickets khi reservation đã confirmed và payment đã succeeded.
- ESB hiện tại có thể bị Booking Service mới từ chối tại bước `bookingTickets`.

### Luồng bắt buộc sau sửa

```text
Payment CAPTURED
→ Seat Service: ConfirmSeats
→ Booking Service: ConfirmReservationEvidence
→ Ticket Service: IssueTickets
→ Booking Service: AttachTickets
→ Booking Service: ConfirmBooking
```

### Cách sửa

1. Tách `_issue_and_confirm()` thành các hàm đơn nhiệm:
   - `_confirm_reservation()`
   - `_record_confirmed_reservation()`
   - `_issue_tickets()`
   - `_attach_tickets()`
   - `_confirm_booking()`
2. Chỉ gọi IssueTickets sau khi Seat Service trả trạng thái `CONFIRMED`.
3. Gọi endpoint Booking mới:

```text
POST /bookings/{booking_id}/reservation-confirmed
operationId: confirmReservationEvidence
```

4. Chỉ gọi ConfirmBooking sau khi Booking Service đã lưu đủ ba evidence:
   - reservation confirmed;
   - payment succeeded;
   - tickets issued.
5. Nếu crash sau ConfirmSeats nhưng trước IssueTickets, reconciliation phải resume từ evidence, không được release ghế ngay khi payment đã captured.

### Test bắt buộc

- ConfirmSeats fail → không có ticket nào được tạo.
- Crash sau ConfirmSeats → reconciliation issue ticket đúng một lần.
- IssueTickets fail sau ConfirmSeats → compensation pending, không xác nhận booking.
- Replay workflow → không tạo ticket trùng.

---

## P0-02 — ESB tự chọn loại vé đầu tiên và tự tính giá

### Source hiện tại

```text
gateway/booking-orchestrator/app/application/booking.py
BookingSaga._authoritative_selection()
BookingSaga._unit_price()
```

### Hành vi hiện tại

- Lấy `event.ticketTypes[0]`.
- Dùng loại vé đầu tiên cho mọi ghế.
- Nhân giá loại vé đầu tiên với số ghế để tạo tổng tiền.

### Vì sao sai

- ESB đang tự chọn sản phẩm khách mua.
- ESB đang sở hữu logic giá.
- Sai khi một booking có nhiều loại ghế hoặc nhiều ticket type.
- Thứ tự phần tử trong mảng Event không phải business rule.

### Cách xử lý đúng mà không thêm nghiệp vụ mới

Public request cũ có thể tiếp tục nhận `seatIds`. ESB không cần tự chọn ticket type. ESB phải lấy dữ liệu authoritative:

```text
seatId → ticketTypeCode: Seat Inventory Service
price(ticketTypeCode): Event Service
```

Luồng đề xuất:

1. Gọi `GetSeatMap(eventId)` từ Seat Service.
2. Với từng `seatId` người dùng chọn:
   - xác định `ticketTypeCode` từ Seat Service;
   - không dùng default `STANDARD`;
   - không dùng phần tử đầu tiên của Event.
3. Gọi Event Service để lấy Event và SaleEligibility.
4. Đối chiếu mỗi `ticketTypeCode` với ticket type authoritative của Event.
5. Tạo `BookingItem` cho từng ghế với unit price lấy từ Event.
6. Tổng tiền được Booking Service kiểm tra và lưu price snapshot; Payment Service kiểm tra lại booking evidence.

### Quy tắc cấm

- Không fallback sang ticket type đầu tiên.
- Không fallback sang `STANDARD` nếu thiếu mapping.
- Không tự sửa mã loại vé.
- Không dùng float.
- Không dùng dữ liệu giá từ frontend làm authority.

### Error cần chuẩn hóa

- `SEAT_NOT_FOUND`
- `TICKET_TYPE_UNAVAILABLE`
- `AUTHORITATIVE_PRICE_MISSING`
- `PRICE_EVIDENCE_MISMATCH`

Chỉ sử dụng error code đã có trong service contract hoặc cập nhật contract qua change request trước khi code.

### Test bắt buộc

- Hai ghế thuộc hai ticket type khác nhau → items và tổng tiền đúng.
- Mảng `ticketTypes` đổi thứ tự → kết quả không đổi.
- Seat trả ticket type không tồn tại trong Event → từ chối booking.
- Frontend giả mạo giá → không ảnh hưởng giá authoritative.

---

## P0-03 — Hard-code `ttlSeconds = 600` trong Saga

### Source hiện tại

```text
gateway/booking-orchestrator/app/application/booking.py
BookingSaga._create_and_reserve()
```

### Hành vi hiện tại

```python
"ttlSeconds": 600
```

### Vì sao sai

Reservation TTL là policy của Seat Inventory hoặc policy integration đã được cấu hình. Literal trong Saga làm ESB sở hữu chính sách giữ ghế và khó thay đổi theo môi trường.

### Cách sửa

Ưu tiên theo thứ tự:

1. Seat Service áp dụng TTL mặc định và contract cho phép ESB không truyền TTL; hoặc
2. ESB đọc TTL từ cấu hình có tên rõ ràng, ví dụ:

```text
ESB_RESERVATION_TTL_SECONDS
```

3. Giá trị cấu hình phải có giới hạn và được test.

Không lấy TTL từ browser.

### File cần sửa

- `app/config.py`
- `app/application/booking.py`
- `.env.example`
- contract Seat nếu muốn `ttlSeconds` optional.

### Test bắt buộc

- Không còn literal `600` trong Saga.
- TTL ngoài giới hạn bị từ chối lúc startup.
- Payload replay ReserveSeats giữ nguyên cùng TTL và cùng fingerprint.

---

## P0-04 — Cancellation Saga thực hiện compensation trước khi Booking Service xác nhận transition

### Source hiện tại

```text
gateway/booking-orchestrator/app/application/cancellation.py
```

### Hành vi hiện tại

1. ESB hủy ticket.
2. ESB refund/cancel payment.
3. ESB release reservation.
4. Sau cùng mới gọi Booking `bookingCancel`.

### Vì sao sai

- Booking Service mới là authority của state transition.
- ESB có thể refund/hủy ticket cho một booking mà Booking Service sau đó từ chối cancel.
- ESB đang tự quyết định full refund bằng `booking.total`.
- ESB tự suy luận payment status cũ và policy compensation.

### Luồng bắt buộc sau sửa

Dùng chính API đã có trong Booking Service mới, không cần tự tạo nghiệp vụ mới:

```text
GET Booking authoritative
GET Payment/Ticket/Reservation evidence
→ POST Booking /cancel với compensationStatus=PENDING
→ Booking Service validate state và chấp nhận hoặc từ chối
→ Nếu được chấp nhận: ESB thực hiện compensation
→ POST Booking /compensation-result
```

Chi tiết:

1. Kiểm tra owner bằng Booking Service.
2. Đọc Booking authoritative và ETag.
3. Gọi:

```text
POST /bookings/{booking_id}/cancel
```

Payload dùng field đúng contract mới:

```json
{
  "reason": "USER_REQUEST",
  "paymentStatus": "...",
  "compensationStatus": "PENDING",
  "evidence": {
    "providerReference": "...",
    "verifiedAt": "..."
  }
}
```

4. Nếu Booking từ chối transition, dừng ngay; không thực hiện side effect.
5. Nếu Booking chấp nhận:
   - Ticket Service tự quyết định ticket có thể cancel.
   - Payment Service tự quyết định payment phải cancel hay refund.
   - Seat Service tự quyết định reservation có thể release.
6. Với full refund theo baseline MVP, gọi canonical refund của Payment mà không để ESB tự tính phí hay partial refund. Nếu contract không khóa full refund, phải có ADR/change request trước.
7. Sau khi thực hiện, gọi:

```text
POST /bookings/{booking_id}/compensation-result
operationId: recordCompensationResult
```

8. Gửi evidence thật của từng bước, không chỉ boolean tổng hợp.

### Không được làm

- Không tự đặt booking thành CANCELLED nếu compensation chưa hoàn tất.
- Không ghi payment là FAILED khi payment đã CAPTURED.
- Không coi refund timeout là refund thất bại cuối cùng.
- Không bỏ qua ticket cancellation failure.

### Test bắt buộc

- Booking từ chối cancel → không có refund/release/cancel ticket.
- Refund timeout → Booking ở COMPENSATION_PENDING và được reconcile.
- Replay cancel cùng Idempotency-Key → không refund hai lần.
- Hai request cancel đồng thời → một workflow authoritative.

---

## P0-05 — ESB chưa tương thích với Booking Service refactor version 2.0.0

### Vấn đề cụ thể

Adapter hiện chỉ map:

```text
reservation
payment-started
payment-result
tickets
confirm
fail
cancel
```

Booking Service mới bổ sung:

```text
POST /bookings/{id}/reservation-confirmed
POST /bookings/{id}/compensation-result
```

Ngoài ra payload hiện tại bị lệch:

| Operation | ESB hiện gửi | Booking contract mới yêu cầu |
|---|---|---|
| fail | `reasonCode` | `failureCode`, `reason`, `compensationStatus`, `evidence` |
| cancel | `reasonCode` | `reason`, `paymentStatus`, `compensationStatus`, `evidence` |
| reservation | evidence cũ | `reservationId`, `reservationVersion`, `reservationExpiresAt`, `evidence` |
| reservation confirmed | chưa gọi | `reservationId`, `reservationVersion`, `evidence` |
| compensation result | chưa gọi | `compensationStatus`, `evidence`, optional `reason` |

### Cách sửa

1. Cập nhật `BookingPort` thành các method có tên cụ thể, không dùng một method `transition(operation: str, ...)` cho mọi command.
2. Cập nhật `BookingRestAdapter` với method riêng:
   - `attach_reservation()`
   - `confirm_reservation()`
   - `start_payment()`
   - `record_payment()`
   - `attach_tickets()`
   - `confirm_booking()`
   - `fail_booking()`
   - `cancel_booking()`
   - `record_compensation_result()`
3. Dùng DTO/TypedDict/Pydantic model tại boundary, tránh dictionary không kiểm soát.
4. Contract test phải validate từng payload gửi downstream theo OpenAPI Booking Service mới.

### File cần sửa

- `app/ports/providers.py`
- `app/adapters/rest/providers.py`
- `app/application/booking.py`
- `app/application/cancellation.py`
- `app/workers/reconciliation.py`
- test adapters và contract tests.

---

## P0-06 — ESB chưa tương thích với Payment Service refactor

### Vấn đề payload CreatePayment

ESB hiện gửi gần dạng:

```json
{
  "bookingId": "...",
  "amount": {
    "amountMinor": 250000,
    "currency": "VND"
  },
  "methodToken": "..."
}
```

Payment Service mới yêu cầu tối thiểu có:

- `bookingId`
- `customerId`
- `currency`
- amount/amountMinor theo schema
- booking evidence khi đối chiếu amount/currency

### Vấn đề status mapping

`PaymentOutcome` của ESB hiện có các giá trị như `CREATED` và `DECLINED`, trong khi Payment Service mới dùng:

```text
PENDING
AUTHORIZED
CAPTURED
UNKNOWN
FAILED
CANCELLED
PARTIALLY_REFUNDED
REFUNDED
```

Trong Cancellation Saga hiện có:

```python
PaymentOutcome(str(payment["status"]))
```

Nếu Payment trả `PENDING` hoặc `PARTIALLY_REFUNDED`, đoạn này có thể ném `ValueError`.

### Cách sửa

1. Đồng bộ enum ESB với contract Payment mới.
2. Không dùng enum provider trực tiếp làm workflow outcome. Tách hai lớp:
   - `ProviderPaymentStatus`: y hệt Payment contract.
   - `PaymentDecision`: `SUCCESS`, `DECLINED`, `UNKNOWN`, `NOT_DISPATCHED`, `COMPENSATION_REQUIRED`.
3. Cập nhật CreatePayment payload:
   - customerId authoritative từ Customer mapping;
   - amount minor và currency authoritative từ Booking/Event evidence;
   - booking evidence đúng schema.
4. Payment decline vẫn được map thành public `402 PAYMENT_DECLINED`, nhưng Booking phải được record payment failure và release seat.
5. Payment timeout/UNKNOWN trả `202`, không đổi thành FAILED.
6. Reconciliation phải gọi Payment Service authoritative; ESB không tự áp kết quả provider.
7. Canonical refund path mới ưu tiên:

```text
POST /payments/{payment_id}/refunds
operationId: createPaymentRefund
```

Giữ legacy `/refund` chỉ trong giai đoạn compatibility nếu cần.

### Test bắt buộc

- CreatePayment contract validation với customerId/currency/evidence.
- PENDING không làm ESB crash.
- PARTIALLY_REFUNDED không làm Cancellation Saga crash.
- UNKNOWN → 202 + reconciliation.
- Decline → release seat + Booking FAILED.
- Callback/reconciliation cập nhật Payment, ESB chỉ đọc kết quả authoritative.

---

## P0-07 — Mutable resource version đang được cache trong memory của adapter

### Source hiện tại

```text
gateway/booking-orchestrator/app/adapters/rest/providers.py
BookingRestAdapter._versions
PaymentRestAdapter._versions
TicketRestAdapter._versions
```

### Vì sao sai

- ESB được thiết kế nhiều stateless tasks sau ALB.
- Mỗi task có một dictionary version riêng.
- Reconciliation có thể chạy trên task khác với task tạo workflow.
- Cache có thể stale và gây `412 PRECONDITION_FAILED` hoặc gửi version sai.
- Version là evidence của workflow, không phải cache toàn cục trong adapter.

### Cách sửa

1. Xóa mutable `_versions` khỏi adapters.
2. Mỗi command method nhận `expected_version` rõ ràng.
3. Lấy version từ một trong hai nguồn:
   - response ngay trước đó trong cùng workflow;
   - workflow evidence đã persist;
   - GET authoritative ngay trước command nếu evidence chưa có.
4. Lưu các version cần resume trong workflow persistence:
   - bookingVersion
   - paymentVersion
   - reservationVersion
   - ticketVersions nếu cần.
5. Adapter chỉ thực hiện transport, không giữ business state.

### Test bắt buộc

- Tạo booking trên ESB task A, reconcile trên task B.
- Restart ESB giữa workflow không làm mất version evidence.
- Concurrent transition trả 412 và được reconcile đúng, không retry mù.

---

## P0-08 — `customerId` public request bị nhận nhưng không được tin cậy hoặc sử dụng nhất quán

### Hiện trạng

- Public contract bắt buộc browser gửi `customerId`.
- Frontend hiện gửi marker `AUTHENTICATED-CUSTOMER`.
- Saga thực tế resolve Customer từ JWT identity mapping.
- `browser_customer_id` chỉ tham gia request hash nhưng không phải authority.

### Rủi ro

- Contract gây hiểu nhầm browser được chọn customer.
- Cùng một booking logic nhưng payload marker khác làm idempotency hash khác.
- Client có thể gửi customerId của người khác dù ESB bỏ qua.

### Cách sửa trong phạm vi hiện tại

Vì tài liệu hiện tại dùng tài khoản đã liên kết Customer và UI-04 chỉ tạo validated draft:

1. Customer authoritative luôn resolve từ JWT subject.
2. Public `customerId` chuyển thành optional/deprecated hoặc loại ở API version mới.
3. Trong giai đoạn tương thích:
   - chấp nhận marker cũ;
   - không đưa marker vào canonical idempotency payload;
   - nếu caller gửi customerId thật, phải đối chiếu với mapping và từ chối khi không khớp.
4. Không tự tạo guest Customer cho đến khi contract chính thức bổ sung nghiệp vụ guest booking.

### Test bắt buộc

- Marker cũ và request mới không customerId tạo cùng canonical workflow khi cùng Idempotency-Key/payload.
- customerId của người khác bị từ chối.
- Identity chưa mapping trả `IDENTITY_NOT_MAPPED`.

---

# PHẦN B — CÁC ACTION ESB TRONG TÀI LIỆU CHƯA ĐƯỢC TRIỂN KHAI ĐẦY ĐỦ

## P1-01 — ESB-02 GetEventDetail chưa tổng hợp Event + Seat availability

### Tài liệu yêu cầu

```text
ESB-02 GetEventDetail: Tổng hợp Event + Seat availability
```

### Source hiện tại

```text
app/application/queries.py
QueryService.get_event()
```

Hiện chỉ proxy:

```text
Event Service → Event
```

Không gọi Seat Service.

### Bổ sung cần thực hiện

Public façade đã được frontend chuẩn bị:

```text
GET /api/events/{eventId}/seat-map
```

ESB cần:

1. Gọi Event Service để lấy event/ticket types.
2. Gọi Seat SOAP `GetSeatMap`.
3. Chuyển XML thành JSON projection.
4. Gắn ticket type name và price từ Event theo `ticketTypeCode`.
5. Không tự tạo trạng thái ghế.
6. Không cache availability vượt TTL an toàn.

### Blocker contract cần kiểm tra

Canonical XSD hiện tại của `GetSeatMapResponse` dùng `SeatRefList` chỉ có:

- seatId
- ticketTypeCode

Trong khi frontend cần status `AVAILABLE/HELD/SOLD/BLOCKED`. Nếu WSDL/XSD chưa trả status, phải sửa Seat contract/service trước. ESB không được giả lập tất cả ghế là AVAILABLE.

### File ESB cần sửa

- `app/ports/providers.py`: thêm `get_seat_map()`
- `app/adapters/soap/seat.py`: implement `GetSeatMap`
- `app/application/queries.py` hoặc module `seat_queries.py`
- `app/api/schemas.py`
- `app/api/router.py`
- `contracts/esb-public-api.yaml`

---

## P1-02 — ESB-04 GetBookingStatus chưa tổng hợp payment/ticket projection đầy đủ

### Hiện trạng

`QueryService.get_booking()` chỉ đọc Booking Service và trả:

- bookingId
- status
- total
- reservationId
- paymentId
- ticketIds

### Tài liệu yêu cầu

```text
Đọc Booking và liên kết payment/ticket.
```

### Bổ sung cần thực hiện

Không nhất thiết nhồi toàn bộ dữ liệu vào một response lớn. Bổ sung các façade owner-scoped:

```text
GET /api/bookings?page=&pageSize=
GET /api/tickets?page=&pageSize=
GET /api/tickets/{ticketId}
GET /api/bookings/{bookingId}/tickets
```

Quy tắc:

- Ownership do Booking/Ticket Service xác nhận.
- Browser không gửi customerId để chứng minh ownership.
- QR token chỉ trả cho owner đúng quyền.
- Không log QR token.
- Booking status vẫn lấy từ Booking Service, không suy luận từ Payment/Ticket.

### Frontend đã chuẩn bị

- Customer booking history: `GET /api/bookings`
- Ticket wallet: `GET /api/tickets`
- Ticket detail: `GET /api/tickets/{ticketId}`

---

## P1-03 — Thiếu façade Admin Event cho UI-10

### Path frontend đã chuẩn bị

```text
POST /api/admin/events
PUT  /api/admin/events/{eventId}
POST /api/admin/events/{eventId}/publish
POST /api/admin/events/{eventId}/pause
POST /api/admin/events/{eventId}/close
POST /api/admin/events/{eventId}/cancel
```

### Vai trò ESB

- Kiểm tra role `ADMIN`.
- Chuyển request sang Event Service.
- Propagate Idempotency-Key, If-Match, Correlation ID và trace context.
- Chuẩn hóa error.

### ESB không được làm

- Không cài state machine Event trong ESB.
- Không tự kiểm tra event có được publish/pause/close/cancel hay không ngoài validation contract cơ bản.
- Không tự tính giá.

### File cần bổ sung/sửa

- `contracts/esb-public-api.yaml`
- `app/api/schemas.py`
- `app/api/router.py`
- `app/ports/providers.py`
- `app/adapters/rest/providers.py`
- module mới đề xuất: `app/application/admin_events.py`

---

## P1-04 — Thiếu façade Check-in cho UI-11

### Path frontend đã chuẩn bị

```text
POST /api/check-in/validate
POST /api/check-in/tickets/{ticketId}
```

### Vai trò ESB

- Chỉ cho role `CHECKIN_STAFF` hoặc `ADMIN`.
- Chuyển QR token đến Ticket Service.
- Với check-in, propagate Idempotency-Key và If-Match.
- Chuẩn hóa `ALREADY_CHECKED_IN`, invalid QR, cancelled ticket.

### ESB không được làm

- Không tự verify chữ ký QR.
- Không tự quyết định Ticket hợp lệ.
- Không tự update trạng thái check-in.

### Security bắt buộc

- Không log raw QR token.
- Giới hạn kích thước request.
- Rate limit validate/check-in theo actor và event.
- Audit actor thực hiện check-in.

---

## P1-05 — Thiếu façade Ticket/QR cho UI-08

### Path cần công bố

```text
GET /api/tickets
GET /api/tickets/{ticketId}
GET /api/bookings/{bookingId}/tickets
```

### Projection tối thiểu theo frontend

- ticketId
- bookingId
- eventId
- seatId
- status
- qrToken hoặc safe QR image projection
- resourceVersion

Event name, venue, startsAt và seat display code có thể được ESB composition từ Event/Seat nếu contract yêu cầu; không được tự tạo dữ liệu.

---

## P1-06 — Thiếu booking list authoritative cho UI lịch sử

Frontend hiện phải fallback local recent booking IDs. Cần façade:

```text
GET /api/bookings?page=1&pageSize=20&status=...
```

ESB phải:

1. Resolve customerId từ JWT mapping.
2. Gọi Booking Service list theo customer.
3. Trả pagination projection.
4. Không cho browser truyền customerId tùy ý.

Admin có thể dùng façade riêng với role `ADMIN`; không mở danh sách toàn hệ thống cho user thường.

---

## P1-07 — Auth public entrypoint chưa thống nhất với nguyên tắc “client chỉ biết ESB”

Hiện browser gọi Identity Service riêng, còn ESB chỉ verify JWT/JWKS.

Cần chốt ADR, không tự sửa im lặng:

### Lựa chọn A — strict ESB entrypoint

Thêm façade:

```text
/api/auth/register
/api/auth/login
/api/auth/refresh
/api/auth/logout
/api/auth/me
```

### Lựa chọn B — Identity là ngoại lệ public

Giữ thiết kế hiện tại nhưng ghi rõ trong kiến trúc và tài liệu rằng:

- business calls chỉ qua ESB;
- Identity là public security authority;
- Realtime chỉ public sau khi nhận one-time ticket từ ESB.

Không triển khai cả hai nửa vời.

---

# PHẦN C — RELIABILITY, SECURITY VÀ OBSERVABILITY CÒN THIẾU

## P1-08 — Outbox retry vô hạn, chưa có DEAD_LETTER

### Source hiện tại

```text
app/workers/outbox.py
```

Hiện tăng attempts và schedule lại vô hạn.

### Cần bổ sung

- `max_attempts` từ config.
- Trạng thái `DEAD_LETTER` hoặc `FAILED_FINAL`.
- lastErrorCode, failedAt.
- metric/alert khi terminal.
- admin/ops redrive có kiểm soát.
- dedup theo messageId/eventId ở consumer.

### Lỗi routing cần sửa

Hiện code dùng:

```python
notification if destination == "notification" else realtime
```

Mọi destination sai chính tả bị gửi sang Realtime. Phải dùng registry/map explicit và từ chối destination không hợp lệ.

---

## P1-09 — Pub/Sub còn gắn cứng Notification và Realtime

Để đáp ứng vai trò publish/subscribe của lab mà không bắt buộc Kafka:

1. Tạo abstraction `EventPublisher`.
2. Topic được map sang danh sách subscriber rõ ràng.
3. Outbox lưu `topic`, `eventId`, `schemaVersion`, `aggregateId`, `occurredAt`, `correlationId`.
4. Mỗi subscriber có delivery record riêng.
5. Notification failure không làm booking fail.

Không cần thêm broker mới nếu HTTP webhook + outbox đáp ứng test; nhưng publisher không được hard-code bằng `if/else` trong worker.

---

## P1-10 — `traceId` đang chứa nguyên `traceparent`

### Source hiện tại

```text
app/api/http.py
```

Error envelope và log đang gán:

```text
traceId = request.headers["traceparent"]
```

Trong contract, `traceId` phải là chuỗi hex 16–32 ký tự, còn `traceparent` có format W3C đầy đủ.

### Cách sửa

- Parse `traceparent`.
- Lưu riêng:
  - `traceparent`: header nguyên bản để propagate.
  - `trace_id`: phần 32 hex.
- Invalid traceparent: tạo trace context mới hoặc bỏ trace, không trả chuỗi sai schema.
- Contract test error envelope.

---

## P1-11 — Contract yêu cầu rate limit WS ticket nhưng source chưa enforce

Public contract có response `429` cho:

```text
POST /api/realtime/ws-tickets
```

Cần triển khai limiter theo:

```text
subject + bookingId + time window
```

Yêu cầu:

- Trả `Retry-After`.
- Lưu metric rate-limit hit.
- Không dùng memory-only limiter trong production nhiều task, trừ khi chấp nhận best effort và ghi rõ.

Các endpoint cần limiter tiếp theo theo tài liệu:

- POST booking.
- Check-in/validate QR.
- Admin command nhạy cảm nếu cần.

---

## P1-12 — Chưa có metrics đầy đủ theo tài liệu

Tối thiểu cần:

```text
esb_request_total
esb_request_duration_seconds
esb_dependency_call_total
esb_dependency_duration_seconds
esb_dependency_timeout_total
esb_retry_total
esb_circuit_open_total
esb_bulkhead_rejected_total
esb_workflow_total{phase}
esb_compensation_total{status}
esb_reconciliation_backlog
esb_outbox_backlog
esb_outbox_dead_letter_total
esb_normalized_error_total{code}
```

Không ghi PII/token/QR/payment token vào label.

---

## P1-13 — Service Registry hiện chỉ là wiring trong `main.py`

Cách hiện tại dùng URL config là chấp nhận được cho lab, nhưng cần refactor để dễ cập nhật:

```text
logical service name → endpoint/audience/adapter
```

Đề xuất module:

```text
app/registry/service_registry.py
```

Yêu cầu:

- Không hard-code IP.
- Validate tất cả critical service endpoint lúc startup.
- Health output chỉ trả logical name, không lộ internal URL.
- Tương thích AWS Service Connect/DNS.

Không cần xây registry server riêng cho đồ án.

---

# PHẦN D — CONTRACT ESB PUBLIC CẦN BỔ SUNG

## 1. Giữ nguyên các operation hiện có

Không xóa hoặc đổi operationId của:

- `publicListEvents`
- `publicGetEvent`
- `placeBooking`
- `publicGetBooking`
- `publicCancelBooking`
- `aggregateHealth`
- `getWorkflowTrace`
- `issueRealtimeWebSocketTicket`
- liveness/readiness

Thay đổi phải additive hoặc có versioning rõ ràng.

## 2. Endpoint additive cần bổ sung

### Customer Web

```text
GET /api/events/{eventId}/seat-map
GET /api/bookings
GET /api/bookings/{bookingId}/tickets
GET /api/tickets
GET /api/tickets/{ticketId}
```

### Admin Web

```text
POST /api/admin/events
PUT  /api/admin/events/{eventId}
POST /api/admin/events/{eventId}/publish
POST /api/admin/events/{eventId}/pause
POST /api/admin/events/{eventId}/close
POST /api/admin/events/{eventId}/cancel
POST /api/check-in/validate
POST /api/check-in/tickets/{ticketId}
```

## 3. PlaceBookingRequest cần làm rõ

### Giữ compatibility

- Tiếp tục hỗ trợ `eventId`, `seatIds`, `paymentMethodToken`.
- `customerId` cũ được deprecate/optional và không được coi là authority.

### Canonical processing

- Customer từ JWT mapping.
- ticketTypeCode theo Seat authoritative mapping.
- price theo Event authoritative data.
- Booking Service lưu snapshot.
- Payment Service kiểm tra amount/currency với booking evidence.

### Contact UI-04

Tài liệu hiện chỉ yêu cầu frontend tạo validated draft. Không tự thêm endpoint create guest customer cho đến khi contract nghiệp vụ chốt.

## 4. Cancel request

Nên công bố body:

```json
{
  "reason": "USER_REQUEST"
}
```

Giữ body optional trong giai đoạn compatibility nếu frontend cũ chưa bật reason. ESB không nhận refund amount từ browser.

## 5. Projection status phải dùng enum đóng

Booking public status phải đồng bộ với Booking Service mới:

```text
PENDING
SEAT_RESERVED
PAYMENT_PROCESSING
CONFIRMED
FAILED
CANCELLED
COMPENSATION_PENDING
```

Không trả workflow status không có trong public schema mà frontend không hiểu.

---

# PHẦN E — CẤU TRÚC REFACTOR ĐỀ XUẤT

## File nên sửa

```text
contracts/esb-public-api.yaml

gateway/booking-orchestrator/app/api/router.py
gateway/booking-orchestrator/app/api/schemas.py
gateway/booking-orchestrator/app/api/http.py

gateway/booking-orchestrator/app/domain/models.py
gateway/booking-orchestrator/app/domain/errors.py

gateway/booking-orchestrator/app/ports/providers.py
gateway/booking-orchestrator/app/ports/repositories.py

gateway/booking-orchestrator/app/adapters/rest/providers.py
gateway/booking-orchestrator/app/adapters/soap/seat.py

gateway/booking-orchestrator/app/application/booking.py
gateway/booking-orchestrator/app/application/cancellation.py
gateway/booking-orchestrator/app/application/queries.py

gateway/booking-orchestrator/app/workers/reconciliation.py
gateway/booking-orchestrator/app/workers/outbox.py

gateway/booking-orchestrator/app/config.py
gateway/booking-orchestrator/app/main.py
```

## Module mới đề xuất

```text
app/application/seat_queries.py
app/application/ticket_queries.py
app/application/admin_events.py
app/application/check_in.py
app/application/booking_history.py

app/registry/service_registry.py
app/messaging/event_publisher.py
app/security/rate_limit.py
app/observability/metrics.py
```

Không bắt buộc tạo đúng tên nếu source có convention khác, nhưng phải giữ separation of concerns.

## Nguyên tắc clean code

- Router chỉ parse/serialize HTTP.
- Application service điều phối use case.
- Adapter chỉ chuyển contract và transport.
- Domain model ESB chỉ chứa workflow/evidence, không chứa domain rule service khác.
- Không dispatch bằng string tùy ý nếu có thể dùng method/type rõ ràng.
- Không giữ mutable provider version trong adapter.
- Không có magic number/string trong Saga.
- Payload downstream phải có type và contract test.
- Không catch `Exception` rồi mất error evidence; phải lưu errorCode và step status.

---

# PHẦN F — WORKFLOW MỤC TIÊU SAU CẬP NHẬT

## 1. PlaceBooking happy path

```text
1. Verify JWT và resolve customer mapping
2. Read Customer ACTIVE
3. Read Event + SaleEligibility
4. Read SeatMap/seat-ticketType mapping
5. Validate selected seats and authoritative price references
6. Create Booking PENDING với item snapshots
7. ReserveSeats
8. AttachReservation vào Booking
9. CreatePayment với booking/customer/amount/currency evidence
10. StartPayment trong Booking
11. AuthorizePayment
12. CapturePayment
13. RecordPaymentResult trong Booking
14. ConfirmSeats
15. ConfirmReservationEvidence trong Booking
16. IssueTickets
17. AttachTickets trong Booking
18. ConfirmBooking
19. Commit ESB workflow + outbox
20. Return 201
```

## 2. Payment decline

```text
ReserveSeats thành công
→ Payment decline authoritative
→ RecordPayment FAILED trong Booking
→ ReleaseSeats
→ FailBooking với compensation evidence
→ Return 402
```

## 3. Payment unknown

```text
Payment command dispatched nhưng outcome không xác định
→ Record Payment UNKNOWN/evidence phù hợp
→ Schedule reconciliation
→ Không release seat mù
→ Return 202 + Location + Retry-After
```

Reservation extension chỉ dùng nếu tài liệu/contract đã khóa và phải có giới hạn `max_reservation_extensions`.

## 4. After-capture failure

```text
Payment CAPTURED
→ bước sau lỗi
→ Booking COMPENSATION_PENDING
→ reconciliation xác định Ticket/Seat/Payment authoritative state
→ thực hiện bù trừ idempotent
→ recordCompensationResult
```

Không đổi payment CAPTURED thành FAILED.

## 5. Cancel booking

```text
Access check
→ Booking cancel command chấp nhận và chuyển COMPENSATION_PENDING
→ cancel tickets
→ cancel/refund payment authoritative
→ release reservation
→ recordCompensationResult
→ Booking CANCELLED khi complete
```

---

# PHẦN G — TEST MATRIX BẮT BUỘC

## Unit tests

- Không chọn ticket type đầu tiên.
- Không hard-code TTL.
- State mapping Booking/Payment đầy đủ.
- Error mapping giữ upstream errorCode.
- W3C trace parsing.
- Explicit outbox destination registry.

## Contract tests

- Runtime OpenAPI ESB bằng canonical OpenAPI.
- Mọi downstream request validate với contract service.
- SOAP request/response validate XSD.
- Legacy public operationId được giữ nguyên.
- Endpoint mới có RBAC và error responses.

## Integration tests

- Happy path đầy đủ với PostgreSQL.
- Nhiều ticket type trong cùng booking.
- Booking Service mới: reservation-confirmed và compensation-result.
- Payment Service mới: PENDING/UNKNOWN/PARTIALLY_REFUNDED.
- Seat map REST→SOAP→REST.
- Ticket detail/QR owner access.
- Admin Event lifecycle.
- Check-in và duplicate check-in.

## Fault tests

- Seat timeout trước dispatch.
- ReserveSeats ambiguous response.
- Payment timeout sau dispatch.
- ConfirmSeats fail sau capture.
- IssueTickets fail sau ConfirmSeats.
- ESB crash và resume trên task khác.
- Notification down không rollback booking.
- Outbox poison message vào DEAD_LETTER.
- Reconciliation worker restart.

## Concurrency/idempotency tests

- Double-click PlaceBooking chỉ một booking.
- Hai workflow cùng ghế tối đa một thành công.
- Replay IssueTickets không tạo vé trùng.
- Replay refund không refund hai lần.
- Hai cancel request đồng thời.
- ESB task A tạo workflow, task B resume.

## Security tests

- User không đọc ticket/booking của user khác.
- User thường không gọi Admin Event.
- User thường không check-in.
- QR/payment token không xuất hiện trong log.
- WS ticket/check-in rate limit trả 429 và Retry-After.

---

# PHẦN H — THỨ TỰ THỰC HIỆN

## Sprint/Pha 1 — Tính đúng và compatibility

- [ ] P0-01 sửa thứ tự ConfirmSeats → IssueTickets.
- [ ] P0-02 xóa lựa chọn ticket type đầu tiên và tính giá trong ESB.
- [ ] P0-03 bỏ TTL literal.
- [ ] P0-04 đảo cancellation thành Booking-authorized-first.
- [ ] P0-05 đồng bộ Booking Service v2.
- [ ] P0-06 đồng bộ Payment Service mới.
- [ ] P0-07 xóa version cache memory trong adapter.
- [ ] P0-08 làm rõ customerId/JWT mapping.
- [ ] Chạy contract + unit + integration happy/failure.

## Sprint/Pha 2 — Façade cho frontend

- [ ] Seat map/availability.
- [ ] Booking history.
- [ ] Ticket list/detail/QR.
- [ ] Admin Event commands.
- [ ] Validate/check-in.
- [ ] Sinh lại frontend types.
- [ ] Chạy Playwright UI-01…UI-12.

## Sprint/Pha 3 — Reliability và vận hành

- [ ] Outbox max attempts + dead-letter + redrive.
- [ ] Event publisher/subscriber abstraction.
- [ ] Traceparent parsing.
- [ ] Rate limiting.
- [ ] Metrics/alerts.
- [ ] Service registry refactor.
- [ ] Multi-task crash/resume tests.

---

# PHẦN I — DEFINITION OF DONE

ESB chỉ được xem là cập nhật hoàn tất khi:

- [ ] Không còn business rule giá, ticket selection, Seat TTL hoặc Payment result trong ESB.
- [ ] Workflow đúng thứ tự theo contract Booking/Payment/Seat/Ticket mới.
- [ ] Mọi transition Booking dùng payload đúng contract version 2.0.0.
- [ ] Payment PENDING/UNKNOWN/refund statuses được xử lý không crash.
- [ ] Không còn provider version cache trong memory adapter.
- [ ] Tất cả public operation cũ vẫn tương thích.
- [ ] Endpoint frontend mới được công bố và type generation pass.
- [ ] Runtime OpenAPI bằng canonical OpenAPI.
- [ ] SOAP transform validate WSDL/XSD.
- [ ] Unit, contract, integration và fault tests pass.
- [ ] Notification/Realtime failure không rollback booking.
- [ ] Outbox có terminal dead-letter và redrive.
- [ ] Correlation ID/trace xuyên suốt và đúng schema.
- [ ] QR/payment token/PII không xuất hiện trong log.
- [ ] Docker Compose smoke/E2E pass.
- [ ] GitHub Actions gateway pipeline xanh.
- [ ] Các phần chưa triển khai được ghi rõ, không tuyên bố PASS khi chưa có runtime evidence.

---

# PHẦN J — NHỮNG THAY ĐỔI KHÔNG ĐƯỢC TỰ Ý THỰC HIỆN

Không tự thêm các nghiệp vụ sau khi chưa có change request/document update:

- Guest checkout tự tạo Customer.
- Partial refund hoặc cancellation fee mới.
- Dynamic pricing.
- Chọn loại vé tự động bằng heuristic.
- Payment provider thật.
- Offline check-in.
- Marketplace/resale.
- Recommendation hoặc promotion engine.
- Shared database hoặc foreign key xuyên service.
- ESB tự đọc/ghi database Customer/Event/Seat/Booking/Payment/Ticket.

---

## Kết luận

ESB hiện tại có nền tảng đúng về routing, REST/SOAP mediation, Saga, idempotency, reconciliation, outbox và error normalization. Tuy nhiên trước đợt mở rộng façade cho frontend, phải sửa các lỗi P0 về thứ tự orchestration, quyền sở hữu giá/ticket type/TTL/cancellation, compatibility Booking–Payment mới và mutable version cache.

Sau khi hoàn thành P0, các façade UI có thể được bổ sung mà không biến ESB thành một god service. ESB chỉ điều phối và chuyển đổi; mọi quyết định domain vẫn thuộc service authoritative.
