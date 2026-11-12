from typing import Any

RETRYABLE_STATUSES = frozenset({409, 429})


class PayPalError(Exception):
    """Base class. `retryable` tells the outbox job whether to retry with the same request ID."""

    retryable: bool = False


class PayPalNotConfigured(PayPalError):
    def __init__(self, what: str = "PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET") -> None:
        super().__init__(f"PayPal is not configured: set {what} in backend/.env")


class PayPalNetworkError(PayPalError):
    """No HTTP response. `outcome_unknown` is True when the request may have reached PayPal,
    so the caller must retry with the same PayPal-Request-Id (or reconcile), never a new one."""

    retryable = True

    def __init__(self, message: str, *, outcome_unknown: bool) -> None:
        super().__init__(message)
        self.outcome_unknown = outcome_unknown


class PayPalApiError(PayPalError):
    def __init__(
        self,
        *,
        status: int,
        name: str,
        message: str,
        issues: tuple[str, ...] = (),
        debug_id: str | None = None,
    ) -> None:
        detail = f"PayPal {status} {name}: {message}"
        if issues:
            detail += f" ({', '.join(issues)})"
        super().__init__(detail)
        self.status = status
        self.name = name
        self.message = message
        self.issues = issues
        self.debug_id = debug_id
        self.retryable = status in RETRYABLE_STATUSES or status >= 500

    def has_issue(self, *issues: str) -> bool:
        return any(issue in self.issues for issue in issues)

    @classmethod
    def from_body(cls, status: int, body: Any, debug_id: str | None) -> "PayPalApiError":
        if not isinstance(body, dict):
            return cls(status=status, name="UNKNOWN", message=str(body)[:500], debug_id=debug_id)
        # REST APIs answer {name, message, details[{issue}]}; OAuth uses {error, error_description}.
        name = str(body.get("name") or body.get("error") or "UNKNOWN")
        message = str(body.get("message") or body.get("error_description") or "")
        details = body.get("details") or []
        issues = tuple(str(d["issue"]) for d in details if isinstance(d, dict) and d.get("issue"))
        return cls(
            status=status,
            name=name,
            message=message,
            issues=issues,
            debug_id=debug_id or body.get("debug_id"),
        )
