"""PayPal REST client (sandbox). Every mutating call is idempotent via PayPal-Request-Id and
recorded through an OperationRecorder; nothing here retries money calls on its own, the outbox
jobs own the retry policy."""

from app.integrations.paypal.client import PayPalClient
from app.integrations.paypal.config import PayPalConfig
from app.integrations.paypal.errors import (
    PayPalApiError,
    PayPalError,
    PayPalNetworkError,
    PayPalNotConfigured,
)

__all__ = [
    "PayPalApiError",
    "PayPalClient",
    "PayPalConfig",
    "PayPalError",
    "PayPalNetworkError",
    "PayPalNotConfigured",
]
