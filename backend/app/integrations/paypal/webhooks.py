from collections.abc import Mapping
from typing import Any

from app.integrations.paypal.errors import PayPalNotConfigured
from app.integrations.paypal.http import PayPalHttp

# PayPal transmission header -> field of the verify-webhook-signature request.
TRANSMISSION_HEADERS = {
    "paypal-auth-algo": "auth_algo",
    "paypal-cert-url": "cert_url",
    "paypal-transmission-id": "transmission_id",
    "paypal-transmission-sig": "transmission_sig",
    "paypal-transmission-time": "transmission_time",
}


async def verify_webhook_signature(
    http: PayPalHttp, headers: Mapping[str, str], event: dict[str, Any]
) -> bool:
    """Ask PayPal whether this delivery is authentic. Missing transmission headers are a
    verification failure, never an exception, so the endpoint can answer 400."""
    if not http.config.webhook_id:
        raise PayPalNotConfigured("PAYPAL_WEBHOOK_ID")
    lowered = {key.lower(): value for key, value in headers.items()}
    fields = {field: lowered.get(header) for header, field in TRANSMISSION_HEADERS.items()}
    if not all(fields.values()):
        return False
    body = {**fields, "webhook_id": http.config.webhook_id, "webhook_event": event}
    response = await http.request("POST", "/v1/notifications/verify-webhook-signature", json=body)
    return isinstance(response.body, dict) and response.body.get("verification_status") == "SUCCESS"
