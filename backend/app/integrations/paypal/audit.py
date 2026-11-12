from dataclasses import dataclass
from typing import Any, Literal, Protocol

OperationKind = Literal[
    "create_order",
    "authorize",
    "capture",
    "void",
    "reauthorize",
    "payout",
    "vault_setup",
    "vault_token",
]


@dataclass(frozen=True)
class Operation:
    """Identifies one logical money call. The same request_id is reused on every retry."""

    kind: OperationKind
    request_id: str
    contract_id: str | None = None


@dataclass(frozen=True)
class OperationRecord:
    operation: Operation
    http_method: str
    path: str
    request_body: Any
    response_status: int | None
    response_body: Any
    paypal_debug_id: str | None


class OperationRecorder(Protocol):
    """Persists the audit trail of every mutating PayPal call (bodies already redacted)."""

    async def record(self, record: OperationRecord) -> None: ...


class NullRecorder:
    async def record(self, record: OperationRecord) -> None:
        return None


def operation_request_id(contract_id: str, operation: OperationKind, attempt_series: int) -> str:
    """Deterministic PayPal-Request-Id: `cov-{contract_id}-{operation}-{n}`. `n` only increases
    after a *definite* failure, so retries after timeouts replay the original request."""
    return f"cov-{contract_id}-{operation}-{attempt_series}"
