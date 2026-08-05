# Identity and Access Service

Standalone FastAPI service for account credentials, roles, access JWTs and
refresh sessions. It owns only Identity data and does not depend on Customer,
Booking, Payment, Ticket or the ESB to run locally.

## Implemented v1 contract

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/auth/register` | Register a CUSTOMER account |
| `POST` | `/auth/login` | Issue access JWT and refresh/CSRF cookies |
| `POST` | `/auth/refresh` | Rotate refresh token and issue a new access JWT |
| `POST` | `/auth/logout` | Revoke the refresh-token family and clear cookies |
| `GET` | `/auth/me` | Read the current Identity principal |
| `POST` | `/admin/users/{userId}/roles` | Assign or revoke a role; requires ADMIN |
| `GET` | `/.well-known/jwks.json` | Publish the RSA verification key |
| `GET` | `/health/live` | Process liveness |
| `GET` | `/health/ready` | PostgreSQL and migration readiness |

The reviewed OpenAPI document is [`../../contracts/identity-service.yaml`](../../contracts/identity-service.yaml) and is served
unchanged at `/openapi.json`.

## Local prerequisites

- Python 3.12
- PostgreSQL installed directly on the computer
- PostgreSQL command-line tools (`psql`) available, or pgAdmin for running SQL

Docker is not required for local development.

## 1. Create the local PostgreSQL role and databases

Run the following as the PostgreSQL administrator. Change the password before
executing it.

```sql
CREATE ROLE identity WITH LOGIN PASSWORD 'change-me';
CREATE DATABASE identity OWNER identity;
CREATE DATABASE identity_test OWNER identity;
```

`identity_test` is separate because integration tests truncate Identity tables.
Never point `IDENTITY_TEST_DATABASE_URL` at data that must be preserved.

The default native PostgreSQL port is `5432`. Confirm it with:

```sql
SHOW port;
```

## 2. Create the Python environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
```

## 3. Create local configuration

Copy the example file:

```powershell
Copy-Item .env.example .env
```

Edit `.env` and replace `change-me` in both database URLs with the password used
when creating the PostgreSQL role. Load this file explicitly into the process
environment; the service does not silently load secret files from source.

Important local values:

```dotenv
IDENTITY_DATABASE_URL=postgresql+psycopg://identity:change-me@localhost:5432/identity
IDENTITY_TEST_DATABASE_URL=postgresql+psycopg://identity:change-me@localhost:5432/identity_test
IDENTITY_ISSUER=http://localhost:8009
IDENTITY_AUDIENCE=public-esb
IDENTITY_COOKIE_SECURE=false
```

If the password contains `@`, `:`, `/`, `#`, `%` or spaces, URL-encode it in the
connection string.

## 4. Generate the local RSA signing key

```powershell
python scripts/generate_keys.py `
  --private-key keys/private.pem `
  --public-key keys/public.pem
```

The `keys/` directory and `.env` are ignored by Git and Docker build context.

## 5. Apply the database migration

```powershell
alembic upgrade head
alembic current
```

Expected current revision:

```text
0001_identity (head)
```

The migration creates the `identity` schema, all Identity tables, constraints,
indexes and the four roles `CUSTOMER`, `ADMIN`, `CHECKIN_STAFF` and `SERVICE`.

## 6. Run the service

```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8009
```

Useful URLs:

- API docs: `http://localhost:8009/docs`
- OpenAPI: `http://localhost:8009/openapi.json`
- Liveness: `http://localhost:8009/health/live`
- Readiness: `http://localhost:8009/health/ready`
- JWKS: `http://localhost:8009/.well-known/jwks.json`
- Metrics: `http://localhost:8009/metrics`

Readiness should return:

```json
{"service":"identity-service","status":"READY","version":"1.0.0"}
```

## 7. Run tests against local PostgreSQL

The test database URL is read from the process environment.

```powershell
pytest
pytest -m integration -v
pytest -m security -v
```

The PostgreSQL-backed tests cover registration/login, CSRF, role authorization,
account lockout, refresh-token reuse and concurrent refresh row locking.

## Bootstrap the first administrator

```powershell
$env:IDENTITY_ADMIN_EMAIL = "admin@example.test"
$env:IDENTITY_ADMIN_PASSWORD = "Use-a-long-local-password-9!Long"
python -m scripts.bootstrap_admin
Remove-Item Env:IDENTITY_ADMIN_PASSWORD
```

Public registration only creates `CUSTOMER`. The bootstrap command is the
controlled path for the first `ADMIN`.

## Local browser input/output rules

Login returns the access token in JSON and sets two cookies:

- `identity_refresh`: HttpOnly refresh token
- `identity_csrf`: readable double-submit CSRF token

Refresh and logout require all of the following:

- `identity_refresh` cookie
- `identity_csrf` cookie
- `X-CSRF-Token` header equal to the CSRF cookie
- An allowed `Origin` when the client sends an Origin header

All endpoints accept optional `X-Correlation-ID` and `traceparent` headers. The
service returns `X-Correlation-ID` and `X-Trace-ID` response headers. Login and
refresh responses use `Cache-Control: no-store`.

## Architecture and security

- Synchronous SQLAlchemy transactions over PostgreSQL schema `identity`
- Argon2id password hashes
- RS256 JWT claims: `iss`, `aud`, `sub`, `iat`, `exp`, `jti`, `roles`,
  `tokenVersion`
- Opaque refresh tokens; only SHA-256 hashes are stored
- Refresh-token family rotation and reuse detection
- PostgreSQL row locking for concurrent refresh safety
- Database-backed rate limiting and audit records
- Deny-by-default authorization dependencies
- Structured logs without passwords, cookies, JWTs, private keys or DSNs

JWT `sub` is the Identity user ID. `customerId` is intentionally not an Identity
claim. When the ESB is connected locally, configure it to expect:

```text
issuer  = http://localhost:8009
audience = public-esb
```

## Quality commands

```powershell
ruff check .
ruff format --check .
mypy app
pytest
pip-audit -r requirements.txt
bandit -r app scripts
```
