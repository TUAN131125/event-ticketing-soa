"""Application-layer outcomes shared across use cases."""

from dataclasses import dataclass

from app.domain.entities import TokenPair


@dataclass(frozen=True, slots=True)
class LoginOutcome:
    token_pair: TokenPair
    session_id: str
