# Admin Web structure

Admin Web chỉ chứa màn hình thuộc UI-10, UI-11 hoặc phục vụ trực tiếp vận hành/truy vết quy trình hiện có.

## Route

- `/login` — đăng nhập qua ESB auth façade và kiểm tra role `ADMIN` từ Identity session.
- `/overview` — aggregate health và bản đồ trạng thái tích hợp.
- `/events` — danh sách/quản lý Event.
- `/events/new` — tạo Event.
- `/events/:eventId/edit` — cập nhật Event và ticket type/giá.
- `/check-in` — validate QR và check-in Ticket.
- `/traces` — tra workflow theo Correlation ID.

## Quy tắc tích hợp

- Browser chỉ gọi ESB cho nghiệp vụ.
- Event mutation dùng `Idempotency-Key` và `If-Match` khi có resource version.
- Check-in dùng `Idempotency-Key` và `If-Match`; Ticket Service giữ quyền quyết định hiệu lực và chống check-in lặp.
- Không dùng API Booking owner-scoped để giả lập quyền quản trị toàn hệ thống.

## Không có trong Admin Web

- Booking Operations dành cho quản trị viên.
- Seat Inventory Administration.
- Payment Operations.
- Notification Operations.
- Users & Roles.

Những màn hình trên không thuộc UI-01 đến UI-12 hoặc chưa có contract quản trị được phân quyền riêng nên không được tự bổ sung.
