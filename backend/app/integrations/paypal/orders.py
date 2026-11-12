from decimal import Decimal
from typing import Any

from app.core.money import format_amount
from app.integrations.paypal.audit import Operation
from app.integrations.paypal.http import PayPalHttp
from app.integrations.paypal.types import Order

DESCRIPTION_MAX_LENGTH = 127


async def create_authorize_order(
    http: PayPalHttp,
    *,
    operation: Operation,
    amount: Decimal,
    reference_id: str,
    custom_id: str,
    invoice_id: str,
    description: str,
    vault_id: str | None = None,
    return_url: str | None = None,
    cancel_url: str | None = None,
) -> Order:
    """Create an `intent=AUTHORIZE` order. With a vault_id PayPal authorizes immediately (status
    COMPLETED with an authorization); without one the payer must approve via payer_action_url."""
    if amount <= 0:
        raise ValueError("Order amount must be positive")
    paypal_source: dict[str, Any]
    if vault_id:
        paypal_source = {"vault_id": vault_id}
    else:
        if not (return_url and cancel_url):
            raise ValueError("return_url and cancel_url are required without a vault_id")
        paypal_source = {
            "experience_context": {
                "brand_name": http.config.brand_name,
                "shipping_preference": "NO_SHIPPING",
                "user_action": "CONTINUE",
                "return_url": return_url,
                "cancel_url": cancel_url,
            }
        }
    body = {
        "intent": "AUTHORIZE",
        "purchase_units": [
            {
                "reference_id": reference_id,
                "custom_id": custom_id,
                "invoice_id": invoice_id,
                "description": description[:DESCRIPTION_MAX_LENGTH],
                "amount": {"currency_code": http.config.currency, "value": format_amount(amount)},
            }
        ],
        "payment_source": {"paypal": paypal_source},
    }
    response = await http.request("POST", "/v2/checkout/orders", json=body, operation=operation)
    return Order.parse(response.body)


async def authorize_order(http: PayPalHttp, order_id: str, *, operation: Operation) -> Order:
    response = await http.request(
        "POST", f"/v2/checkout/orders/{order_id}/authorize", json={}, operation=operation
    )
    return Order.parse(response.body)


async def get_order(http: PayPalHttp, order_id: str) -> Order:
    response = await http.request("GET", f"/v2/checkout/orders/{order_id}")
    return Order.parse(response.body)
