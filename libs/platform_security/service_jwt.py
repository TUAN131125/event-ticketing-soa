"""RS256 service identity tokens with strict claim and replay validation."""

from __future__ import annotations

import base64
import binascii
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import jwt


class ServiceAuthenticationError(ValueError):
    """Raised when an internal service credential cannot be trusted."""


@dataclass(frozen=True, slots=True)
class ServicePrincipal:
    subject: str
    roles: frozenset[str]
    token_id: str


@dataclass(frozen=True, slots=True)
class ServiceJwtValidationSettings:
    public_key_path: Path | None
    public_key_base64: str | None
    issuer: str
    audience: str
    allowed_subjects: frozenset[str]

    @classmethod
    def from_environment(
        cls,
        prefix: str,
        *,
        audience: str,
        default_allowed_subjects: str = "booking-orchestrator",
    ) -> ServiceJwtValidationSettings:
        path_value = os.getenv(f"{prefix}_SERVICE_JWT_PUBLIC_KEY_PATH", "").strip()
        base64_value = os.getenv(f"{prefix}_SERVICE_JWT_PUBLIC_KEY_BASE64", "").strip()
        issuer = os.getenv(f"{prefix}_SERVICE_JWT_ISSUER", "").strip()
        configured_audience = os.getenv(
            f"{prefix}_SERVICE_JWT_AUDIENCE", audience
        ).strip()
        subjects = frozenset(
            item.strip()
            for item in os.getenv(
                f"{prefix}_ALLOWED_SERVICE_SUBJECTS", default_allowed_subjects
            ).split(",")
            if item.strip()
        )
        if not issuer:
            raise ValueError(f"{prefix}_SERVICE_JWT_ISSUER is required")
        return cls(
            Path(path_value) if path_value else None,
            base64_value or None,
            issuer,
            configured_audience,
            subjects,
        )

    def verifier(self) -> ServiceJwtVerifier:
        return ServiceJwtVerifier(
            public_key=load_key_material(
                path=self.public_key_path,
                base64_value=self.public_key_base64,
                label="Service JWT public key",
            ),
            issuer=self.issuer,
            audience=self.audience,
            allowed_subjects=self.allowed_subjects,
        )


@dataclass(frozen=True, slots=True)
class ServiceJwtSigningSettings:
    private_key_path: Path | None
    private_key_base64: str | None
    issuer: str
    subject: str
    key_id: str
    ttl_seconds: int

    @classmethod
    def from_environment(
        cls, prefix: str, *, default_subject: str
    ) -> ServiceJwtSigningSettings:
        path_value = os.getenv(f"{prefix}_SERVICE_JWT_PRIVATE_KEY_PATH", "").strip()
        base64_value = os.getenv(f"{prefix}_SERVICE_JWT_PRIVATE_KEY_BASE64", "").strip()
        issuer = os.getenv(f"{prefix}_SERVICE_JWT_ISSUER", "").strip()
        subject = os.getenv(f"{prefix}_SERVICE_JWT_SUBJECT", default_subject).strip()
        key_id = os.getenv(f"{prefix}_SERVICE_JWT_KEY_ID", "").strip()
        try:
            ttl = int(os.getenv(f"{prefix}_SERVICE_JWT_TTL_SECONDS", "60"))
        except ValueError as exc:
            raise ValueError(
                f"{prefix}_SERVICE_JWT_TTL_SECONDS must be an integer"
            ) from exc
        if not issuer or not subject or not key_id:
            raise ValueError(
                f"{prefix} Service JWT issuer, subject and key id are required"
            )
        return cls(
            Path(path_value) if path_value else None,
            base64_value or None,
            issuer,
            subject,
            key_id,
            ttl,
        )

    def signer(self) -> ServiceJwtSigner:
        return ServiceJwtSigner(
            private_key=load_key_material(
                path=self.private_key_path,
                base64_value=self.private_key_base64,
                label="Service JWT private key",
            ),
            issuer=self.issuer,
            subject=self.subject,
            key_id=self.key_id,
            ttl_seconds=self.ttl_seconds,
        )


def load_key_material(
    *, path: str | Path | None, base64_value: str | None, label: str
) -> str:
    """Load exactly one PEM source without writing secret material to the repository."""
    if path and base64_value:
        raise ValueError(f"Configure only one of {label} file or Base64 value")
    if path:
        try:
            value = Path(path).read_text(encoding="utf-8")
        except OSError as exc:
            raise ValueError(f"Cannot read {label} file: {path}") from exc
    elif base64_value:
        try:
            value = base64.b64decode(base64_value, validate=True).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError) as exc:
            raise ValueError(f"{label} Base64 value is invalid") from exc
    else:
        raise ValueError(f"{label} file or Base64 value is required")
    if "-----BEGIN" not in value:
        raise ValueError(f"{label} is not PEM encoded")
    return value


class ServiceJwtSigner:
    """Issue short-lived Service JWTs for one configured service identity."""

    def __init__(
        self,
        *,
        private_key: str,
        issuer: str,
        subject: str,
        key_id: str,
        ttl_seconds: int = 60,
    ) -> None:
        if not issuer or not subject or not key_id:
            raise ValueError("Service JWT issuer, subject and key id are required")
        if not 1 <= ttl_seconds <= 300:
            raise ValueError("Service JWT TTL must be between 1 and 300 seconds")
        self._private_key = private_key
        self._issuer = issuer
        self._subject = subject
        self._key_id = key_id
        self._ttl_seconds = ttl_seconds

    def issue(self, audience: str) -> str:
        if not audience:
            raise ValueError("Service JWT audience is required")
        now = int(time.time())
        return jwt.encode(
            {
                "iss": self._issuer,
                "sub": self._subject,
                "aud": audience,
                "roles": ["SERVICE"],
                "iat": now,
                "exp": now + self._ttl_seconds,
                "jti": str(uuid4()),
            },
            self._private_key,
            algorithm="RS256",
            headers={"kid": self._key_id},
        )


class ServiceJwtVerifier:
    """Verify Service JWT cryptography, claims, identity and one-time token use."""

    def __init__(
        self,
        *,
        public_key: str,
        issuer: str,
        audience: str,
        allowed_subjects: frozenset[str],
        max_token_age_seconds: int = 300,
        leeway_seconds: int = 5,
    ) -> None:
        if not issuer or not audience or not allowed_subjects:
            raise ValueError(
                "Service JWT issuer, audience and allowed subjects are required"
            )
        self._public_key = public_key
        self._issuer = issuer
        self._audience = audience
        self._allowed_subjects = allowed_subjects
        self._max_token_age_seconds = max_token_age_seconds
        self._leeway_seconds = leeway_seconds
        self._seen: dict[str, int] = {}
        self._lock = threading.Lock()

    def verify_authorization(self, authorization: str | None) -> ServicePrincipal:
        if not authorization or not authorization.startswith("Bearer "):
            raise ServiceAuthenticationError("Bearer Service JWT is required")
        token = authorization.removeprefix("Bearer ").strip()
        if not token or " " in token:
            raise ServiceAuthenticationError("Bearer Service JWT is malformed")
        try:
            header = jwt.get_unverified_header(token)
            if header.get("alg") != "RS256" or not header.get("kid"):
                raise ServiceAuthenticationError("Service JWT header is invalid")
            claims = jwt.decode(
                token,
                self._public_key,
                algorithms=["RS256"],
                issuer=self._issuer,
                audience=self._audience,
                leeway=self._leeway_seconds,
                options={
                    "require": ["iss", "sub", "aud", "roles", "iat", "exp", "jti"],
                },
            )
        except ServiceAuthenticationError:
            raise
        except jwt.PyJWTError as exc:
            raise ServiceAuthenticationError("Service JWT validation failed") from exc

        subject = claims.get("sub")
        roles = claims.get("roles")
        token_id = claims.get("jti")
        issued_at = claims.get("iat")
        expires_at = claims.get("exp")
        if not isinstance(subject, str) or subject not in self._allowed_subjects:
            raise ServiceAuthenticationError("Service identity is not allowed")
        if (
            not isinstance(roles, list)
            or "SERVICE" not in roles
            or any(not isinstance(role, str) for role in roles)
        ):
            raise ServiceAuthenticationError("Service role is required")
        if not isinstance(token_id, str) or not token_id:
            raise ServiceAuthenticationError("Service JWT jti is invalid")
        if not isinstance(issued_at, int) or not isinstance(expires_at, int):
            raise ServiceAuthenticationError("Service JWT timestamps are invalid")
        now = int(time.time())
        if (
            issued_at > now + self._leeway_seconds
            or now - issued_at > self._max_token_age_seconds
        ):
            raise ServiceAuthenticationError("Service JWT issue time is invalid")
        self._reject_replay(token_id, expires_at, now)
        return ServicePrincipal(subject, frozenset(roles), token_id)

    def _reject_replay(self, token_id: str, expires_at: int, now: int) -> None:
        with self._lock:
            self._seen = {
                key: expiry for key, expiry in self._seen.items() if expiry >= now
            }
            if token_id in self._seen:
                raise ServiceAuthenticationError("Service JWT replay detected")
            self._seen[token_id] = expires_at + self._leeway_seconds
