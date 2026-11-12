"""Vault v3 for a PayPal wallet without a purchase: setup token → payer approves →
payment token. Orders then pass the payment token as `payment_source.paypal.vault_id`."""

from app.integrations.paypal.audit import Operation
from app.integrations.paypal.errors import PayPalApiError
from app.integrations.paypal.http import PayPalHttp
from app.integrations.paypal.types import PaymentToken, SetupToken

VAULT_DESCRIPTION = "Covenant escrow: holds for agreed work, captured only for work that passes"


async def create_setup_token(
    http: PayPalHttp, *, operation: Operation, return_url: str, cancel_url: str
) -> SetupToken:
    body = {
        "payment_source": {
            "paypal": {
                "description": VAULT_DESCRIPTION,
                "usage_type": "MERCHANT",
                "usage_pattern": "IMMEDIATE",
                "experience_context": {
                    "brand_name": http.config.brand_name,
                    "shipping_preference": "NO_SHIPPING",
                    "return_url": return_url,
                    "cancel_url": cancel_url,
                },
            }
        }
    }
    response = await http.request("POST", "/v3/vault/setup-tokens", json=body, operation=operation)
    return SetupToken.parse(response.body)


async def create_payment_token(
    http: PayPalHttp, setup_token_id: str, *, operation: Operation
) -> PaymentToken:
    body = {"payment_source": {"token": {"id": setup_token_id, "type": "SETUP_TOKEN"}}}
    response = await http.request(
        "POST", "/v3/vault/payment-tokens", json=body, operation=operation
    )
    return PaymentToken.parse(response.body)


async def delete_payment_token(http: PayPalHttp, payment_token_id: str) -> None:
    """Idempotent: a token PayPal no longer knows is already gone."""
    try:
        await http.request("DELETE", f"/v3/vault/payment-tokens/{payment_token_id}")
    except PayPalApiError as exc:
        if exc.status != 404:
            raise
