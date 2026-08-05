# Tiêu chuẩn contract của Event Ticketing SOA

## 1. Nguồn sự thật và phạm vi publish

- Thư mục `/contracts` là nguồn sự thật duy nhất cho mọi giao diện runtime.
- Mỗi REST service sở hữu đúng một OpenAPI 3.1 tự chứa. `$ref` chỉ được trỏ tới fragment trong chính file đó.
- Seat Inventory sở hữu đúng một WSDL 1.1 và một XSD 1.0 chính thức.
- Realtime tách HTTP bằng OpenAPI và WebSocket bằng AsyncAPI.
- Mọi event nghiệp vụ dùng một JSON Schema Draft 2020-12 duy nhất: `event-messages.schema.json`.
- `CONTRACT_STANDARD.md`, `CONTRACT_REVIEW.md` và `manifest.yaml` là metadata quản trị, không phải contract runtime và không được publish như artifact riêng.
- `dist/contracts/manifest.json` là manifest của lần build; nó chứa SHA-256 của từng artifact nhưng không phải một domain contract.

## 2. Version và compatibility

- Baseline hiện tại là `1.0.0`; OpenAPI dùng `3.1.0`, AsyncAPI dùng `3.0.0` và JSON Schema dùng Draft 2020-12.
- Xóa operation/response, thêm input bắt buộc, thu hẹp type/enum, đổi security, namespace SOAP, SOAP action hoặc fault là breaking change.
- Contract mục tiêu đã review có ưu tiên cao hơn route/model runtime cũ. Drift phải được ghi vào `CONTRACT_REVIEW.md`, không được hợp thức hóa bằng alias hoặc API song song.

## 3. Port chuẩn

| Boundary | Port |
|---|---:|
| ESB Public API | 8000 |
| Customer Service | 8001 |
| Event Service | 8002 |
| Seat Inventory | 8003 |
| Booking Service | 8004 |
| Payment Service | 8005 |
| Ticket Service | 8006 |
| Notification Service | 8007 |
| Realtime Service | 8008 |
| Identity Service | 8009 |

Contract chỉ dùng endpoint local để mô tả port. Host triển khai phải đến từ cấu hình môi trường, không được đưa hostname production vào source.

## 4. HTTP metadata và tracing

- Mọi HTTP operation nhận `X-Correlation-ID` và W3C `traceparent`; service tạo correlation ID nếu caller không gửi và truyền tiếp qua downstream call.
- Mọi lỗi trả lại `correlationId`; `traceId` được trả khi có thể công bố an toàn.
- Command có thể retry dùng `Idempotency-Key`. Cùng key và cùng payload phải trả cùng kết quả; cùng key nhưng payload khác trả `409`.
- Resource có version trả strong `ETag`; mutation phụ thuộc version nhận `If-Match`. ETag không khớp trả `412`.
- `GET /health/live` kiểm tra process; `GET /health/ready` kiểm tra dependency bắt buộc. Hai endpoint không yêu cầu authentication.

## 5. Kiểu dữ liệu chuẩn

Money được khai báo cục bộ trong contract cần dùng, không qua file dùng chung:

```json
{"amountMinor": 250000, "currency": "VND"}
```

- `amountMinor` là integer không âm; không truyền số tiền bằng floating point.
- `currency` là mã ISO 4217 gồm ba ký tự in hoa.
- Timestamp dùng RFC 3339 và biểu diễn UTC bằng `Z` hoặc `+00:00`.
- Identifier là opaque string; consumer không suy luận cấu trúc nội bộ.

## 6. Security scheme

- `UserJwt`: access JWT ngắn hạn do Identity phát; kiểm tra tối thiểu signature, `iss`, `aud`, `exp`, `sub`, `roles` và `tokenVersion`.
- `ServiceJwt`: JWT ngắn hạn cho service-to-service; kiểm tra `iss`, `sub`, `aud`, `iat`, `exp`, `jti`, allow-list caller và replay.
- `WebhookHmac`: HMAC-SHA256 trên `X-Webhook-Timestamp + "." + rawBody`; kiểm tra timestamp window trước khi xử lý.
- Cookie refresh/CSRF của Identity và signed one-time WebSocket ticket là cơ chế chuyên biệt được mô tả ngay trong contract sở hữu chúng.
- Không đưa secret, token mẫu dùng được, password, private key hoặc URL production vào contract.

## 7. Error envelope

Mọi REST error dùng đúng envelope sau:

```json
{
  "correlationId": "corr-1234567890abcdef",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "error": {
    "code": "RESOURCE_CONFLICT",
    "message": "The resource changed; reload and retry.",
    "retryable": false,
    "details": {"currentVersion": 3}
  }
}
```

`details` chỉ chứa dữ liệu an toàn; không trả stack trace, credential, URL nội bộ, raw SOAP/XML hoặc PII không cần thiết. SOAP dùng `SeatServiceFault` tương đương về `correlationId`, `code`, `message` và `retryable`.

## 8. Realtime và event

- HTTP ingestion/health của Realtime nằm trong `realtime-service.openapi.yaml`; WebSocket `/ws/bookings/{bookingId}` nằm trong `realtime-service.asyncapi.yaml`.
- Browser lấy signed ticket từ ESB, gửi ticket trong frame `authenticate` trong vòng năm giây và không truyền credential trong URL.
- Ticket có TTL tối đa 60 giây, chỉ dùng một lần và ràng buộc đúng `bookingId`.
- Realtime là projection best-effort; `GET /api/bookings/{bookingId}` là nguồn trạng thái authoritative.
- Event delivery là at-least-once; producer cấp `eventId`, `correlationId`, `occurredAt`, `aggregateId` và consumer deduplicate theo `eventId`.

## 9. Quy trình thay đổi

1. Sửa artifact canonical trong `/contracts` và cập nhật `manifest.yaml` nếu inventory thay đổi.
2. Cập nhật example ngay trong contract và ghi drift mới vào `CONTRACT_REVIEW.md`.
3. Chạy `python contracts/scripts/validate_contracts.py`.
4. Chạy `python contracts/scripts/build_contracts.py`.
5. Chỉ triển khai provider/consumer alignment trong task business riêng; không sửa contract để che drift runtime.
