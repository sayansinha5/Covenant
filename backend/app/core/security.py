import hashlib
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.core.ids import new_request_id

JWT_ALGORITHM = "HS256"
PASSWORD_MIN_LENGTH = 12
PASSWORD_MAX_LENGTH = 128

_hasher = PasswordHasher()  # argon2id with the library's current recommended parameters
# Verified against when the email is unknown, so failed logins take the same time either way.
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(16))


def password_problems(password: str) -> list[str]:
    problems = []
    if len(password) < PASSWORD_MIN_LENGTH:
        problems.append(f"at least {PASSWORD_MIN_LENGTH} characters")
    if len(password) > PASSWORD_MAX_LENGTH:
        problems.append(f"at most {PASSWORD_MAX_LENGTH} characters")
    if not re.search(r"[A-Za-z]", password):
        problems.append("one letter")
    if not re.search(r"\d", password):
        problems.append("one number")
    return problems


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def new_opaque_token() -> str:
    """256 bits of randomness, URL-safe (refresh tokens, API key secrets)."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass(frozen=True)
class AccessClaims:
    user_id: str
    org_id: str | None
    role: str | None
    jti: str
    expires_at: datetime


class InvalidToken(Exception):
    pass


@dataclass(frozen=True)
class TokenIssuer:
    secret: str
    issuer: str
    audience: str
    ttl: timedelta

    def issue(self, *, user_id: str, org_id: str | None, role: str | None) -> tuple[str, int]:
        now = datetime.now(UTC)
        claims: dict[str, Any] = {
            "iss": self.issuer,
            "aud": self.audience,
            "sub": user_id,
            "org": org_id,
            "role": role,
            "iat": int(now.timestamp()),
            "exp": int((now + self.ttl).timestamp()),
            "jti": new_request_id(),
        }
        return jwt.encode(claims, self.secret, algorithm=JWT_ALGORITHM), int(
            self.ttl.total_seconds()
        )

    def decode(self, token: str) -> AccessClaims:
        try:
            claims = jwt.decode(
                token,
                self.secret,
                algorithms=[JWT_ALGORITHM],
                audience=self.audience,
                issuer=self.issuer,
                options={"require": ["iss", "aud", "sub", "iat", "exp", "jti"]},
            )
        except jwt.PyJWTError as exc:
            raise InvalidToken(str(exc)) from exc
        return AccessClaims(
            user_id=str(claims["sub"]),
            org_id=claims.get("org"),
            role=claims.get("role"),
            jti=str(claims["jti"]),
            expires_at=datetime.fromtimestamp(claims["exp"], UTC),
        )
