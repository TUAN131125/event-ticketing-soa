# Event Ticketing SOA

Đây là bộ khung thư mục cho hệ thống đặt vé sự kiện theo kiến trúc SOA/ESB.

## Trạng thái

- Chưa chứa mã nguồn triển khai.
- Các tệp hiện tại chỉ là placeholder hợp lệ để mở và tổ chức trong Visual Studio Code.
- Có thể xóa nội dung placeholder khi bắt đầu phát triển.
- Dùng `event-ticketing-soa.code-workspace` để mở toàn bộ project trong VS Code.

## Thành phần chính

- `frontend/`: Customer Web và Admin Web.
- `gateway/`: ESB / Booking Orchestrator.
- `services/`: Các service nghiệp vụ.
- `contracts/`: OpenAPI, WSDL/XSD và JSON Schema.
- `database/`: Schema, migration, seed và script dữ liệu.
- `tests/`: Contract, integration, fault, performance và security test.
- `infra/`: Docker và hạ tầng AWS.
- `monitoring/`: Log, metric, trace và dashboard.
- `docs/`: Tài liệu từ Giai đoạn 1 đến Giai đoạn 8.
- `evidence/`: Bằng chứng CI/CD, test, AWS và demo.
- `.github/workflows/`: Pipeline GitHub Actions.

Xem toàn bộ cây thư mục trong `PROJECT_TREE.txt`.
