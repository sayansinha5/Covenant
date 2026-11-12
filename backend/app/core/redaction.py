from collections.abc import Mapping
from typing import Any

REDACTED = "[redacted]"
SENSITIVE_SUBSTRINGS = ("secret", "password", "vault", "api_key", "apikey", "cookie")
SENSITIVE_EXACT = frozenset({"authorization", "token", "access_token", "refresh_token", "id_token"})


def is_sensitive_key(key: str) -> bool:
    # Exact match for "authorization" so PayPal's `authorizations` list (IDs we need) survives.
    lowered = key.lower().replace("-", "_")
    return (
        lowered in SENSITIVE_EXACT
        or lowered.endswith("_token")
        or any(part in lowered for part in SENSITIVE_SUBSTRINGS)
    )


def redact(value: Any) -> Any:
    """Return a deep copy of JSON-like data with every sensitive key's value replaced."""
    if isinstance(value, Mapping):
        return {
            key: REDACTED if is_sensitive_key(str(key)) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list | tuple):
        return [redact(item) for item in value]
    return value
