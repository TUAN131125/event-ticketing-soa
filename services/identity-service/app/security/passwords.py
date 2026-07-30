"""Argon2id password hashing and verification."""

from __future__ import annotations

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.config import Settings


class PasswordService:
    def __init__(self, settings: Settings) -> None:
        self._hasher = PasswordHasher(
            time_cost=settings.argon2_time_cost,
            memory_cost=settings.argon2_memory_cost_kib,
            parallelism=settings.argon2_parallelism,
            hash_len=32,
            salt_len=16,
            type=Type.ID,
        )
        self._dummy_hash = self._hasher.hash(
            "Dummy-Password-Only-For-Timing-Equalization-9!"
        )

    @property
    def dummy_hash(self) -> str:
        return self._dummy_hash

    def hash(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify(self, encoded_hash: str, password: str) -> bool:
        try:
            return bool(self._hasher.verify(encoded_hash, password))
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False

    def needs_rehash(self, encoded_hash: str) -> bool:
        try:
            return bool(self._hasher.check_needs_rehash(encoded_hash))
        except InvalidHashError:
            return True
