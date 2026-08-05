# Contract review và implementation drift

Review này đối chiếu contract mục tiêu với tài liệu Giai đoạn 3/Giai đoạn 5 còn được phản ánh trong catalog cũ, `gateway/booking-orchestrator/ESB_IMPLEMENTATION_PLAN.md`, route/model hiện tại, ESB adapter và frontend usage. Contract trong `/contracts` là quyết định mục tiêu; các mục dưới đây là backlog alignment, không phải lý do để giữ API cũ song song.

## Tổng quan

| Boundary | Trạng thái hiện tại | Mismatch còn lại |
|---|---|---|
| ESB Public API | Partial | Tám operation lõi đã có trong orchestrator, nhưng frontend đang gọi thêm nhiều route không có trong public contract. Adapter Seat/Realtime còn dùng authentication và namespace cũ. |
| Identity | Gần khớp | Route chính, JWKS và health đã hiện diện. Runtime từng phục vụ bản contract local; reference đã chuyển sang bản canonical root. Provider conformance cho tên security scheme/metadata mới vẫn cần task riêng. |
| Customer | Drift | Runtime chỉ có CRUD cơ bản, `exists`, deactivate và `/health`; thiếu lookup, consent, identity link/unlink/resolve và health split. Error/header/security chưa theo chuẩn. |
| Event | Drift | Runtime dùng `open-sales`, `pause-sales`, `close-sales`, `on-sale`; contract dùng publish/pause/cancel và sale eligibility có pricing authoritative. Money runtime chưa dùng `amountMinor`. |
| Seat Inventory | Drift nghiêm trọng | Service-local WSDL/runtime và ESB adapter dùng namespace `urn:event-ticketing:seat-inventory:v1`, action/fault/shape khác contract `urn:event-ticketing:seat:v1` + `SeatServiceFault`. Runtime dùng static service token thay vì Service JWT. |
| Booking | Drift | Runtime có create/list/get/confirm/fail/cancel; thiếu reservation, payment-started/result, tickets evidence transition, customer-scoped list và access-decision. Tên operation/shape/versioning khác contract. |
| Payment | Drift | Runtime dùng `/refund` thay vì `/refunds`, thiếu provider callback contract, và model tiền là decimal + currency rời thay vì `Money`. Callback/UNKNOWN/reconciliation semantics chưa đồng nhất. |
| Ticket | Drift | Runtime dùng `/tickets/issue` thay vì `/tickets:issue`, `/qr/regenerate` thay vì `/reissue-qr`; thiếu by-booking và validate route mục tiêu. |
| Notification | Drift nghiêm trọng | Runtime nhận hai webhook riêng, unsigned, trả `200`; contract nhận generic signed `POST /webhooks/events`, HMAC, dedupe eventId và trả `202`. Runtime chỉ có `/health`. |
| Realtime | Drift | Runtime có HTTP health và one-time-ticket path, nhưng internal ingress vẫn dùng `X-Service-Token`; native subprotocol/query-token fallback và frame `pong`/`connected` khác AsyncAPI authenticate/subscribe/heartbeat protocol. |
| Event messages | Drift | Service outbox/envelope hiện chưa cùng dùng một validator/schema tổng hợp và một số producer vẫn serialize money/timestamp theo model cũ. |

## ESB adapter và orchestration

- `gateway/booking-orchestrator/app/adapters/soap/seat.py` còn tạo XML theo namespace cũ, tìm `SeatInventoryFault`, đổi `ttlSeconds` thành `holdSeconds`, gửi `schemaVersion=1.0` và dùng `X-Service-Token`; tất cả khác WSDL/XSD mục tiêu.
- REST adapter metadata trước đây trỏ tới `openapi/*.yaml`; reference đã chuyển sang file flat. Việc adapter thực sự kiểm tra schema/request/response vẫn chưa được triển khai.
- Realtime adapter gửi static token và `X-Caller-Service`, trong khi OpenAPI yêu cầu Service JWT ngắn hạn có audience/JTI/replay policy.
- Notification adapter tạo timestamp epoch giây, còn contract HMAC header khai báo RFC 3339 UTC. Cần thống nhất signing input trong task provider/consumer alignment.
- Orchestrator đang giữ freeze constant/hash của catalog cũ. Contract task chuyển integrity check sang `manifest.yaml`/SHA build; thay đổi Saga và provider call order không nằm trong scope này.

## Frontend usage

- Customer Web gọi `/api/events/{eventId}/seats`, các route reservation, `GET /api/bookings`, `/api/tickets/{ticketId}`; các route này không thuộc ESB public contract mục tiêu hiện tại.
- Customer Web vẫn có `native-subprotocol` và gửi access token qua WebSocket subprotocol; contract mục tiêu chỉ cho phép signed one-time ticket trong frame `authenticate`.
- Client trả `pong` khi nhận heartbeat, trong khi AsyncAPI dùng `heartbeat_ack` có `heartbeatId`; client cũng chờ `connected` thay vì `authenticated`.
- TypeScript model còn dùng `price`/`total` dạng number cộng `currency` rời, chưa theo `Money {amountMinor, currency}`.
- Admin Web gọi overview, event mutation, booking list/refund, payment, notification, monitoring trace và user routes chưa được công bố trong ESB public contract.
- Environment example từng trỏ Realtime vào 8007 hoặc qua đường dẫn ESB 8000; reference cấu hình đã được sửa về WebSocket service port 8008, nhưng feature alignment vẫn cần task frontend riêng.

## Port và operational surface

- Contract đã khóa public/local port 8000–8009 đúng bảng trong `CONTRACT_STANDARD.md`.
- Nhiều Docker image chạy internal port 8000 rồi map host port chuẩn; đây không phải contract drift nếu deployment mapping giữ đúng public port.
- Customer, Event và Notification runtime hiện chỉ có `/health`; cần bổ sung `/health/live` và `/health/ready` trong task implementation riêng.
- Realtime, Booking, Payment, Ticket và Identity đã có cặp health runtime; ESB contract bổ sung cặp health chuẩn ngoài aggregate `/api/health`.

## Quyết định không thực hiện trong task này

- Không đổi route handler, domain state machine, repository, migration hoặc database schema.
- Không thêm alias để duy trì cả endpoint cũ và endpoint mục tiêu.
- Không đổi amount decimal hiện tại sang amountMinor trong business model.
- Không thay static credential bằng JWT trong runtime; chỉ contract hóa yêu cầu và ghi drift.
- Không sửa WebSocket state machine, Saga hoặc delivery behavior.
