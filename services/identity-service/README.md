# Identity and Access Service

Security-critical REST service for account credentials, roles, access tokens and
refresh sessions. Identity owns authentication data only; Customer, Booking,
Payment and Ticket data remain in their own services.

## Architecture and security decisions

- FastAPI with synchronous SQLAlchemy transactions and PostgreSQL schema identity.
- Argon2id password hashes; raw passwords never enter logs or database rows.
- RS256 access JWTs with iss, aud, sub, iat, exp, jti, roles, tokenVersion and
  rotating kid-selected keys.
- Opaque 64-byte refresh tokens. Only SHA-256 token hashes are stored.
- Refresh sessions are grouped into families. A token is consumed once; reuse
  revokes the whole family. Two concurrent refreshes are serialized by the
  PostgreSQL row lock, so only one can succeed.
- Refresh tokens are HttpOnly cookies. Refresh and logout use double-submit CSRF
  plus an Origin allow-list. Access tokens are returned in JSON.
- Logout revokes refresh sessions; an already issued access JWT remains valid until
  expiry unless the user's tokenVersion changes, for example after a role change.
- Authorization is deny-by-default and centralized in FastAPI dependencies.
- Login rate-limit buckets and audit records are database-backed, so replicas share state.

The project material describes Identity but does not provide a canonical Giai đoạn 5
OpenAPI or migration. This directory therefore contains the executable contract at
contracts/identity-service.yaml and migration 0001_identity. Role names and JWT
claims are intentionally stable for ESB consumers.

## Local setup

Requirements: Python 3.12, Docker Desktop and PostgreSQL.

~~~powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
$env:IDENTITY_DATABASE_URL = "postgresql+psycopg://identity:identity@localhost:5434/identity"
python scripts/generate_keys.py --private-key keys/private.pem --public-key keys/public.pem
alembic upgrade head
uvicorn app.main:app --reload --port 8009
~~~

Or run the complete local stack:

~~~powershell
docker compose up --build
~~~

The API is at http://localhost:8009, docs are at /docs, and JWKS is at
/.well-known/jwks.json. Production must use HTTPS, Secure cookies and managed
private key material; local defaults are not production credentials.

## Bootstrap an administrator

Never commit an admin password. Supply it through the environment or an interactive
prompt after the database and signing keys exist:

~~~powershell
$env:IDENTITY_ADMIN_EMAIL = "admin@example.test"
$env:IDENTITY_ADMIN_PASSWORD = "Use-a-long-local-password-9!Long"
python -m scripts.bootstrap_admin
Remove-Item Env:IDENTITY_ADMIN_PASSWORD
~~~

Public registration can only create CUSTOMER. The bootstrap script is the
controlled path for the first ADMIN.

## Endpoint examples

Register:

~~~powershell
curl.exe -X POST http://localhost:8009/auth/register -H "Content-Type: application/json" -d '{"email":"customer@example.test","password":"Correct-Horse-9!Long"}'
~~~

Login stores the refresh and CSRF cookies in a normal browser client and returns
the access token:

~~~powershell
curl.exe -i -c cookies.txt -X POST http://localhost:8009/auth/login -H "Content-Type: application/json" -d '{"email":"customer@example.test","password":"Correct-Horse-9!Long"}'
~~~

Call /auth/me with the returned Bearer access token. For refresh/logout, send the
identity_refresh and identity_csrf cookies plus the exact CSRF cookie value in
X-CSRF-Token; clients should also send an allowed Origin.

## Migration and test commands

~~~powershell
alembic upgrade head
alembic downgrade base
alembic upgrade head
ruff check .
ruff format --check .
mypy app
pytest
pytest -m integration
pip-audit -r requirements.txt
bandit -r app scripts
~~~

Integration and concurrency tests require a real PostgreSQL database. Set
IDENTITY_TEST_DATABASE_URL to a migrated test database; tests never use SQLite as
a substitute for transaction semantics.

## Operational contract

/health/live only reports process liveness. /health/ready checks PostgreSQL, the
identity schema and Alembic revision. The application sets readiness to draining
during graceful shutdown. Structured logs include operation, status, duration,
correlation and trace IDs, but never credentials, cookies, JWTs, Authorization
headers, private keys or database DSNs. /metrics exposes bounded Prometheus labels
for request/authentication/session signals.
