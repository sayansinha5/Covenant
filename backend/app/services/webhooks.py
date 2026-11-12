"""PayPal webhooks: verify and store on receipt (answering fast), then apply in the
`webhook.process` job. Processing is idempotent by PayPal event ID and only applies what is
valid from the current state, so duplicate, early and out-of-order deliveries are harmless."""

import json
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.core.logging import get_logger
from app.db.base import utcnow
from app.domain.state_machine import Job
from app.integrations.paypal import PayPalClient, PayPalError, PayPalNotConfigured
from app.integrations.paypal.types import Authorization, Capture, PayoutBatch, PayoutItem
from app.models import Contract, Escrow, Payout, PayPalFundingAccount, WebhookEvent
from app.services import escrow as escrows
from app.services import payouts
from app.services.outbox import enqueue
from app.services.paypal_sync import (
    Result,
    Sync,
    capture_reported,
    hold_authorized,
    hold_released,
    ignored,
    payout_item_reported,
)

logger = get_logger("covenant.webhooks")

# Payout item events whose resource may omit the final `transaction_status`.
ITEM_EVENT_STATUSES = {
    "PAYMENT.PAYOUTS-ITEM.SUCCEEDED": "success",
    "PAYMENT.PAYOUTS-ITEM.FAILED": "failed",
    "PAYMENT.PAYOUTS-ITEM.BLOCKED": "failed",
    "PAYMENT.PAYOUTS-ITEM.DENIED": "failed",
    "PAYMENT.PAYOUTS-ITEM.CANCELED": "failed",
    "PAYMENT.PAYOUTS-ITEM.UNCLAIMED": "unclaimed",
    "PAYMENT.PAYOUTS-ITEM.RETURNED": "returned",
    "PAYMENT.PAYOUTS-ITEM.REFUNDED": "returned",
}
MAX_ID_LENGTH = 64


class WebhookRejected(AppError):
    status = 400
    code = "WEBHOOK_REJECTED"
    title = "Webhook rejected"


class WebhookUnavailable(AppError):
    status = 503
    code = "WEBHOOK_UNAVAILABLE"
    title = "Webhook not accepted"


async def receive(
    session: AsyncSession, paypal: PayPalClient, headers: Mapping[str, str], body: bytes
) -> str:
    """Verify one delivery with PayPal and store it. Returns `accepted` or `duplicate`."""
    try:
        event = json.loads(body)
    except ValueError:
        raise WebhookRejected("The body isn't valid JSON.") from None
    if not (
        isinstance(event, dict)
        and isinstance(event.get("id"), str)
        and isinstance(event.get("event_type"), str)
    ):
        raise WebhookRejected("This isn't a PayPal webhook event.")
    event_id = event["id"][:MAX_ID_LENGTH]
    event_type = event["event_type"][:MAX_ID_LENGTH]

    try:
        verified = await paypal.verify_webhook_signature(headers, event)
    except PayPalNotConfigured:
        raise WebhookUnavailable(
            "Webhooks aren't set up on this server: set PAYPAL_WEBHOOK_ID."
        ) from None
    except PayPalError:
        # 503 makes PayPal deliver it again later.
        raise WebhookUnavailable("We couldn't verify this webhook with PayPal.") from None

    if not verified:
        session.add(
            WebhookEvent(
                paypal_event_id=None,
                event_type=event_type,
                verified=False,
                payload={"claimed_event_id": event_id},
                error="Signature verification failed.",
            )
        )
        await session.commit()
        logger.warning("webhook_rejected", claimed_event_id=event_id, event_type=event_type)
        raise WebhookRejected("The webhook signature couldn't be verified.")

    if await session.scalar(
        select(WebhookEvent.id).where(WebhookEvent.paypal_event_id == event_id)
    ):
        return "duplicate"
    resource = event.get("resource")
    resource_id = resource.get("id") if isinstance(resource, dict) else None
    row = WebhookEvent(
        paypal_event_id=event_id,
        event_type=event_type,
        resource_id=str(resource_id)[:MAX_ID_LENGTH] if resource_id else None,
        verified=True,
        payload=event,
    )
    session.add(row)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        return "duplicate"
    await enqueue(
        session,
        Job.PROCESS_WEBHOOK,
        {"webhook_event_id": row.id},
        dedupe_key=f"{Job.PROCESS_WEBHOOK}:{row.id}",
    )
    await session.commit()
    logger.info("webhook_accepted", event_id=event_id, event_type=event_type)
    return "accepted"


async def process(session: AsyncSession, settings: Settings, webhook_event_id: str) -> None:
    row = await session.scalar(
        select(WebhookEvent)
        .where(WebhookEvent.id == webhook_event_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if row is None or row.processed or not row.verified:
        return
    handler = HANDLERS.get(row.event_type)
    resource = row.payload.get("resource")
    if handler is None:
        contract_id, outcome = None, ignored("Covenant doesn't act on this event type.")
    elif not isinstance(resource, dict):
        contract_id, outcome = None, ignored("The event has no resource.")
    else:
        try:
            contract_id, outcome = await handler(
                Context(session, settings, row.event_type, row.paypal_event_id or row.id), resource
            )
        except (KeyError, TypeError, ValueError) as exc:
            contract_id, outcome = None, ignored(f"The event resource couldn't be read: {exc!r}")
    row.contract_id = contract_id
    row.result = outcome.result
    row.outcome = outcome.message[:500]
    row.processed = True
    row.processed_at = utcnow()
    row.error = None


async def record_failure(session: AsyncSession, webhook_event_id: str, error: str) -> None:
    row = await session.get(WebhookEvent, webhook_event_id)
    if row is not None:
        row.error = error


@dataclass(frozen=True, slots=True)
class Context:
    session: AsyncSession
    settings: Settings
    event_type: str
    event_id: str


Handled = tuple[str | None, Sync]
Handler = Callable[[Context, dict[str, Any]], Awaitable[Handled]]


async def _escrow_contract(
    session: AsyncSession,
    *,
    authorization_id: str | None = None,
    capture_id: str | None = None,
    contract_id: str | None = None,
) -> str | None:
    conditions = []
    if authorization_id:
        conditions.append(Escrow.paypal_authorization_id == authorization_id)
    if capture_id:
        conditions.append(Escrow.paypal_capture_id == capture_id)
    if contract_id:
        conditions.append(Escrow.contract_id == contract_id)
    if not conditions:
        return None
    return await session.scalar(select(Escrow.contract_id).where(or_(*conditions)).limit(1))


async def _locked(ctx: Context, contract_id: str | None) -> tuple[Contract, Escrow] | None:
    if contract_id is None:
        return None
    locked = await escrows.lock_for_paypal(ctx.session, contract_id)
    if locked is None:
        return None
    contract, escrow = locked
    return (contract, escrow) if escrow is not None else None


NO_CONTRACT: Handled = (None, ignored("No Covenant contract matches this event."))


async def _authorization_created(ctx: Context, resource: dict[str, Any]) -> Handled:
    authorization = Authorization.parse(resource)
    contract_id = await _escrow_contract(
        ctx.session, authorization_id=authorization.id, contract_id=authorization.custom_id
    )
    locked = await _locked(ctx, contract_id)
    if locked is None:
        return NO_CONTRACT
    contract, escrow = locked
    return contract.id, await hold_authorized(
        ctx.session, ctx.settings, contract, escrow, authorization
    )


async def _authorization_voided(ctx: Context, resource: dict[str, Any]) -> Handled:
    authorization = Authorization.parse(resource)
    locked = await _locked(
        ctx, await _escrow_contract(ctx.session, authorization_id=authorization.id)
    )
    if locked is None:
        return NO_CONTRACT
    contract, escrow = locked
    return contract.id, await hold_released(ctx.session, contract, escrow, authorization.status)


async def _capture(ctx: Context, resource: dict[str, Any]) -> Handled:
    capture = Capture.parse(resource)
    related = (resource.get("supplementary_data") or {}).get("related_ids") or {}
    contract_id = await _escrow_contract(
        ctx.session, authorization_id=related.get("authorization_id"), capture_id=capture.id
    )
    locked = await _locked(ctx, contract_id)
    if locked is None:
        return NO_CONTRACT
    contract, escrow = locked
    return contract.id, await capture_reported(ctx.session, contract, escrow, capture)


async def _locked_payout(ctx: Context, *conditions: Any) -> tuple[Contract, Payout] | None:
    present = [c for c in conditions if c is not None]
    if not present:
        return None
    contract_id = await ctx.session.scalar(select(Payout.contract_id).where(or_(*present)).limit(1))
    if contract_id is None:
        return None
    payout = await payouts.locked_payout(ctx.session, contract_id)
    if payout is None:
        return None
    return await ctx.session.get_one(Contract, contract_id), payout


async def _payout_batch(ctx: Context, resource: dict[str, Any]) -> Handled:
    batch = PayoutBatch.parse(resource)
    locked = await _locked_payout(
        ctx,
        Payout.paypal_batch_id == batch.batch_id,
        Payout.sender_batch_id == batch.sender_batch_id if batch.sender_batch_id else None,
    )
    if locked is None:
        return NO_CONTRACT
    contract, payout = locked
    if payout.status not in payouts.OPEN_STATUSES:
        return contract.id, ignored(f"Payout is already {payout.status}.")
    if batch.batch_status == "DENIED":
        payouts.fail(ctx.session, contract, payout, "PayPal denied the payout batch.")
        return contract.id, Sync(Result.FIXED, "Payout failed: PayPal denied the batch.")
    payout.paypal_batch_id = payout.paypal_batch_id or batch.batch_id
    await enqueue(
        ctx.session,
        Job.SYNC_PAYOUT,
        {"contract_id": contract.id},
        dedupe_key=f"{Job.SYNC_PAYOUT}:{payout.id}:{ctx.event_id}",
    )
    return contract.id, Sync(Result.IN_SYNC, "Checking the payout item with PayPal.")


def _contract_number(sender_item_id: str | None) -> int | None:
    if sender_item_id and sender_item_id.startswith("C-") and sender_item_id[2:].isdigit():
        return int(sender_item_id[2:])
    return None


async def _payout_item(ctx: Context, resource: dict[str, Any]) -> Handled:
    item = PayoutItem.parse(resource)
    batch_id = resource.get("payout_batch_id")
    number = _contract_number(item.sender_item_id)
    by_number = (
        Payout.contract_id.in_(select(Contract.id).where(Contract.number == number))
        if number is not None
        else None
    )
    locked = await _locked_payout(
        ctx,
        Payout.paypal_item_id == item.item_id,
        Payout.paypal_batch_id == batch_id if batch_id else None,
        by_number,
    )
    if locked is None:
        return NO_CONTRACT
    contract, payout = locked
    status = payouts.FINAL_ITEM_STATUSES.get(item.transaction_status) or ITEM_EVENT_STATUSES.get(
        ctx.event_type
    )
    return contract.id, payout_item_reported(ctx.session, contract, payout, item, status)


async def _payment_token_deleted(ctx: Context, resource: dict[str, Any]) -> Handled:
    account = await ctx.session.scalar(
        select(PayPalFundingAccount)
        .where(
            PayPalFundingAccount.vault_token_id == str(resource["id"]),
            PayPalFundingAccount.status == "connected",
        )
        .with_for_update()
    )
    if account is None:
        return None, ignored("No connected PayPal account uses this payment token.")
    account.status = "disconnected"
    return None, Sync(
        Result.FIXED, "The saved PayPal account was removed in PayPal; the hirer must reconnect."
    )


HANDLERS: dict[str, Handler] = {
    "PAYMENT.AUTHORIZATION.CREATED": _authorization_created,
    "PAYMENT.AUTHORIZATION.VOIDED": _authorization_voided,
    "PAYMENT.CAPTURE.COMPLETED": _capture,
    "PAYMENT.CAPTURE.PENDING": _capture,
    "PAYMENT.CAPTURE.DENIED": _capture,
    "PAYMENT.PAYOUTSBATCH.SUCCESS": _payout_batch,
    "PAYMENT.PAYOUTSBATCH.DENIED": _payout_batch,
    **dict.fromkeys(ITEM_EVENT_STATUSES, _payout_item),
    "VAULT.PAYMENT-TOKEN.DELETED": _payment_token_deleted,
}
