Dat file `identity-public.pem` (public key RS256 cua Identity Service,
xem `services/identity-service/app/security/tokens.py`) vao thu muc nay
truoc khi chay `docker compose up` - notification-service can file nay
de xac minh Bearer JWT cho cac endpoint Admin/Ops (`GET/POST /deliveries*`,
`PUT /templates/{code}`).

Neu chua co file nay, cac endpoint tren se luon tra 401
(`NOTIFICATION_JWT_PUBLIC_KEY_PATH` khong tro toi file ton tai) - webhook
`POST /webhooks/events` van hoat dong binh thuong vi khong yeu cau JWT.
