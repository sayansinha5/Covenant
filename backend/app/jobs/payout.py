"""`payout.send` pays the provider `captured - fee`; `payout.sync` polls PayPal every 30 s for
up to 10 minutes, after which webhooks and reconciliation take over."""

from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.domain.policy import usd
from app.domain.state_machine import Job
from app.integrations.paypal import PayPalApiError
from app.jobs.base import JobContext, JobHandler, Payload, RetryLater
from app.models import Contract
from app.services import payouts
from app.services.contracts import note
from app.services.outbox import enqueue

SYNC_INTERVAL = timedelta(seconds=30)
SYNC_ATTEMPTS = 21  # 30 s apart: about 10 minutes
PAYOUTS_OFF = "Payouts are turned off on this server. An admin can send it later."
NO_EMAIL = "The provider hasn't set a PayPal email for payouts. Update it in Settings."


async def send(session: AsyncSession, ctx: JobContext, payload: Payload) -> None:
    contract = await session.get_one(Contract, payload["contract_id"])
    payout = await payouts.locked_payout(session, contract.id)
    if payout is None or payout.status != "pending" or payout.paypal_batch_id:
        return
    if not ctx.settings.paypal_payouts_enabled:
        note(
            session,
            contract,
            f"Payout of {usd(payout.net)} is pending: {PAYOUTS_OFF}",
            actor=payouts.PAYPAL,
        )
        return
    if not payout.receiver_email:
        payouts.fail(session, contract, payout, NO_EMAIL)
        return
    try:
        batch = await ctx.paypal.create_payout(
            payout_id=payout.id,
            contract_id=contract.id,
            receiver_email=payout.receiver_email,
            amount=payout.net,
            sender_item_id=f"C-{contract.number}",
            note=f"Payment for Covenant contract C-{contract.number}: {contract.title}",
            email_subject=f"You've been paid for C-{contract.number}",
        )
    except PayPalApiError as exc:
        if exc.retryable:
            raise
        payouts.fail(session, contract, payout, exc.message or exc.name)
        return
    payout.paypal_batch_id = batch.batch_id
    if batch.items:
        payout.paypal_item_id = batch.items[0].item_id
    note(
        session,
        contract,
        f"Sent {usd(payout.net)} to {payout.receiver_email} through PayPal Payouts.",
        actor=payouts.PAYPAL,
        data={"payout_batch_id": batch.batch_id},
    )
    await enqueue(
        session,
        Job.SYNC_PAYOUT,
        {"contract_id": contract.id},
        dedupe_key=f"{Job.SYNC_PAYOUT}:{payout.id}",
        run_after=utcnow() + SYNC_INTERVAL,
        max_attempts=SYNC_ATTEMPTS,
    )


async def sync(session: AsyncSession, ctx: JobContext, payload: Payload) -> None:
    contract = await session.get_one(Contract, payload["contract_id"])
    payout = await payouts.locked_payout(session, contract.id)
    if payout is None or payout.status != "pending" or payout.paypal_batch_id is None:
        return
    batch = await ctx.paypal.get_payout_batch(payout.paypal_batch_id)
    item = batch.items[0] if batch.items else None
    if batch.batch_status == "DENIED":
        payouts.fail(session, contract, payout, "PayPal denied the payout batch.")
        return
    status = payouts.FINAL_ITEM_STATUSES.get(item.transaction_status) if item else None
    if item is None or status is None:
        raise RetryLater("PayPal is still processing the payout", delay_seconds=30)
    payouts.apply_item_status(session, contract, payout, item, status)


async def send_give_up(
    session: AsyncSession, ctx: JobContext, payload: Payload, error: str
) -> None:
    contract = await session.get_one(Contract, payload["contract_id"])
    payout = await payouts.locked_payout(session, contract.id)
    if payout is not None and payout.status == "pending" and payout.paypal_batch_id is None:
        payouts.fail(
            session, contract, payout, "We couldn't reach PayPal to send it. An admin can retry."
        )


SEND_HANDLER = JobHandler(run=send, on_give_up=send_give_up)
SYNC_HANDLER = JobHandler(run=sync)
