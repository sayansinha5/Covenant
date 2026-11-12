from decimal import Decimal

from app.core.money import format_amount
from app.integrations.paypal.audit import Operation
from app.integrations.paypal.http import PayPalHttp
from app.integrations.paypal.types import PayoutBatch


def payout_sender_batch_id(payout_id: str) -> str:
    return f"cov-payout-{payout_id}"


async def create_payout(
    http: PayPalHttp,
    *,
    payout_id: str,
    contract_id: str | None,
    receiver_email: str,
    amount: Decimal,
    sender_item_id: str,
    note: str,
    email_subject: str,
) -> PayoutBatch:
    """Send one email payout. Idempotent twice over: PayPal-Request-Id replays the original
    response on retry, and PayPal rejects any reuse of the sender_batch_id."""
    if amount <= 0:
        raise ValueError("Payout amount must be positive")
    sender_batch_id = payout_sender_batch_id(payout_id)
    body = {
        "sender_batch_header": {
            "sender_batch_id": sender_batch_id,
            "recipient_type": "EMAIL",
            "email_subject": email_subject,
            "email_message": note,
        },
        "items": [
            {
                "recipient_type": "EMAIL",
                "receiver": receiver_email,
                "amount": {"value": format_amount(amount), "currency": http.config.currency},
                "sender_item_id": sender_item_id,
                "note": note,
            }
        ],
    }
    operation = Operation(kind="payout", request_id=sender_batch_id, contract_id=contract_id)
    response = await http.request("POST", "/v1/payments/payouts", json=body, operation=operation)
    return PayoutBatch.parse(response.body)


async def get_payout_batch(http: PayPalHttp, payout_batch_id: str) -> PayoutBatch:
    response = await http.request("GET", f"/v1/payments/payouts/{payout_batch_id}")
    return PayoutBatch.parse(response.body)
