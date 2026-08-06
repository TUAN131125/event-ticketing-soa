# Frontend integration status

## Boundary

- Frontend chỉ dùng ESB `/api/auth/*` cho register/login/refresh/logout/current user; Identity là provider nội bộ của ESB.
- Mọi nghiệp vụ Customer/Event/Seat/Booking/Payment/Ticket/Notification đi qua ESB.
- Realtime WebSocket chỉ là projection; REST Booking vẫn authoritative.
- `contracts/esb-public-api.yaml` là nguồn wire contract duy nhất.

## API đã khóa với ESB

### Customer Web

- `GET /api/events`
- `GET /api/events/{eventId}`
- `GET /api/events/{eventId}/seat-map`
- `POST /api/bookings`
- `GET /api/bookings`
- `GET /api/bookings/{bookingId}`
- `POST /api/bookings/{bookingId}/cancel`
- `GET /api/tickets`
- `GET /api/tickets/{ticketId}`
- `POST /api/realtime/ws-tickets`

### Admin Web

- Event create/replace/publish/pause/close/cancel dưới `/api/admin/events`.
- `POST /api/check-in/validate`.
- `POST /api/check-in/tickets/{ticketId}`.
- `GET /api/health` và `GET /api/traces/{correlationId}`.

## Contract rules

- Booking create không gửi `customerId`; ESB resolve Customer từ JWT.
- UI-04 contact là validated client draft, không phải ESB request field.
- Event chỉ dùng field Event Service hỗ trợ; không có `description` hoặc `imageUrl`.
- Ticket không giả lập QR image/timestamp; owner detail dùng `qrToken` authoritative.
- Mutation dùng `Idempotency-Key`; optimistic concurrency dùng ETag/If-Match.
- `frontend-esb-contract.ts` lấy request/response từ `operations[...]` và chỉ dùng `components['schemas']` cho scalar/schema dùng chung.

## Khả năng chịu lỗi

- HTTP deadline 15 giây cho auth façade, Customer Web ESB client và Admin Web ESB client.
- Booking `202` không bị resend; frontend polling trạng thái authoritative.
- WebSocket reconnect dùng one-time ticket mới và REST resync.
- Error code và Correlation ID được hiển thị khi server cung cấp.
- Customer contact PII không được lưu vào localStorage/sessionStorage.

Xem `ESB_FRONTEND_BACKEND_CONTRACT_ALIGNMENT.md` để biết mapping từng projection tới backend authoritative.
