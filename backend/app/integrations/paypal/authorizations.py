from decimal import Decimal

from app.core.money import format_amount
from app.integrations.paypal.audit import Operation
from app.integrations.paypal.errors import PayPalApiError
from app.integrations.paypal.http import PayPalHttp
from app.integrations.paypal.types import Authorization, Capture

NOTE_TO_PAYER_MAX_LENGTH = 255
# Statuses after which a void has nothing left to cancel.
VOID_FINAL_STATUSES = frozenset({"VOIDED", "EXPIRED"})


async def get_authorization(http: PayPalHttp, authorization_id: str) -> Authorization:
    response = await http.request("GET", f"/v2/payments/authorizations/{authorization_id}")
    return Authorization.parse(response.body)


async def capture_authorization(
    http: PayPalHttp,
    authorization_id: str,
    *,
    operation: Operation,
    amount: Decimal,
    invoice_id: str,
    note_to_payer: str,
    final_capture: bool = True,
) -> Capture:
    """Capture all or part of an authorization. With final_capture=True PayPal releases the
    uncaptured remainder of the hold back to the payer."""
    if amount <= 0:
        raise ValueError("Capture amount must be positive; void instead")
    body = {
        "amount": {"currency_code": http.config.currency, "value": format_amount(amount)},
        "final_capture": final_capture,
        "invoice_id": invoice_id,
        "note_to_payer": note_to_payer[:NOTE_TO_PAYER_MAX_LENGTH],
    }
    response = await http.request(
        "POST",
        f"/v2/payments/authorizations/{authorization_id}/capture",
        json=body,
        operation=operation,
    )
    return Capture.parse(response.body)


async def void_authorization(
    http: PayPalHttp, authorization_id: str, *, operation: Operation
) -> Authorization:
    """Void the hold. Idempotent: if PayPal rejects the void because the authorization is
    already voided or expired, the current authorization is returned as the result."""
    try:
        response = await http.request(
            "POST",
            f"/v2/payments/authorizations/{authorization_id}/void",
            json={},
            operation=operation,
        )
    except PayPalApiError as exc:
        if exc.status != 422:
            raise
        current = await get_authorization(http, authorization_id)
        if current.status in VOID_FINAL_STATUSES or exc.has_issue("AUTHORIZATION_EXPIRED"):
            return current
        raise
    if response.body:
        return Authorization.parse(response.body)
    return await get_authorization(http, authorization_id)


async def reauthorize_authorization(
    http: PayPalHttp, authorization_id: str, *, operation: Operation, amount: Decimal
) -> Authorization:
    """Renew a hold after the 3-day honour period. Returns the *new* authorization."""
    body = {"amount": {"currency_code": http.config.currency, "value": format_amount(amount)}}
    response = await http.request(
        "POST",
        f"/v2/payments/authorizations/{authorization_id}/reauthorize",
        json=body,
        operation=operation,
    )
    return Authorization.parse(response.body)
