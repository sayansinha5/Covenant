from datetime import timedelta

import jwt
import pytest

from app.core.security import (
    InvalidToken,
    TokenIssuer,
    hash_password,
    password_problems,
    verify_password,
)

ISSUER = TokenIssuer(
    secret="unit-test-secret-at-least-32-bytes-long",
    issuer="covenant-api",
    audience="covenant-web",
    ttl=timedelta(minutes=15),
)


def test_password_rules() -> None:
    assert password_problems("correct horse battery 9") == []
    assert password_problems("short1") == ["at least 12 characters"]
    assert password_problems("123456789012") == ["one letter"]
    assert password_problems("no numbers here") == ["one number"]


def test_password_hash_round_trip() -> None:
    hashed = hash_password("correct horse battery 9")
    assert hashed.startswith("$argon2id$")
    assert verify_password(hashed, "correct horse battery 9")
    assert not verify_password(hashed, "correct horse battery 8")
    assert not verify_password(None, "correct horse battery 9")
    assert not verify_password("not-a-hash", "anything")


def test_access_token_round_trip() -> None:
    token, expires_in = ISSUER.issue(user_id="u1", org_id="o1", role="owner")
    claims = ISSUER.decode(token)
    assert (claims.user_id, claims.org_id, claims.role) == ("u1", "o1", "owner")
    assert expires_in == 900


def test_expired_token_is_rejected() -> None:
    expired = TokenIssuer(ISSUER.secret, ISSUER.issuer, ISSUER.audience, timedelta(seconds=-1))
    token, _ = expired.issue(user_id="u1", org_id=None, role=None)
    with pytest.raises(InvalidToken):
        ISSUER.decode(token)


@pytest.mark.parametrize(
    "other",
    [
        TokenIssuer(
            "another-secret-at-least-32-bytes-long", "covenant-api", "covenant-web", ISSUER.ttl
        ),
        TokenIssuer(ISSUER.secret, "someone-else", "covenant-web", ISSUER.ttl),
        TokenIssuer(ISSUER.secret, "covenant-api", "another-app", ISSUER.ttl),
    ],
)
def test_foreign_tokens_are_rejected(other: TokenIssuer) -> None:
    token, _ = other.issue(user_id="u1", org_id=None, role=None)
    with pytest.raises(InvalidToken):
        ISSUER.decode(token)


def test_unsigned_token_is_rejected() -> None:
    token = jwt.encode(
        {"iss": "covenant-api", "aud": "covenant-web", "sub": "u1"}, key=None, algorithm="none"
    )
    with pytest.raises(InvalidToken):
        ISSUER.decode(token)
