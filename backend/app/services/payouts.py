"""Payout bookkeeping shared by the payout jobs, webhooks and reconciliation. A payout's status
never changes the contract: the hirer's side is settled once the capture completed."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.policy import usd
from app.domain.state_machine import Ledger
from app.integrations.paypal.types import PayoutItem
from app.models import Contract, Payout
from app.services import ledger
from app.services.contracts import Actor, note

PAYPAL = Actor("paypal")
# PayPal payout item statuses that end polling, mapped to ours.
FINAL_ITEM_STATUSES = {
    "SUCCESS": "success",
    "FAILED": "failed",
    "BLOCKED": "failed",
    "DENIED": "failed",
    "REFUNDED": "returned",
    "RETURNED": "returned",
    "REVERSED": "returned",
    "UNCLAIMED": "unclaimed",
}
# An unclaimed payout can still be claimed, or PayPal returns it after 30 days.
OPEN_STATUSES = ("pending", "unclaimed")


async def locked_payout(session: AsyncSession, contract_id: str) -> Payout | None:
    return await session.scalar(
        select(Payout)
        .where(Payout.contract_id == contract_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


def fail(session: AsyncSession, contract: Contract, payout: Payout, reason: str) -> None:
    payout.status = "failed"
    payout.failure_reason = reason
    note(session, contract, f"Payout failed: {reason}", actor=PAYPAL)


def apply_item_status(
    session: AsyncSession, contract: Contract, payout: Payout, item: PayoutItem, status: str
) -> bool:
    """Move an open payout to PayPal's final item status. Returns False if nothing changed."""
    if payout.status not in OPEN_STATUSES or payout.status == status:
        return False
    payout.paypal_item_id = item.item_id
    if status == "success":
        payout.status = "success"
        payout.failure_reason = None
        ledger.record(
            session,
            org_id=payout.provider_org_id,
            contract=contract,
            direction=Ledger.PAID_OUT,
            amount=payout.net,
            actor=PAYPAL,
            paypal_reference=item.item_id,
        )
        note(session, contract, f"PayPal paid out {usd(payout.net)}.", actor=PAYPAL)
    elif status == "unclaimed":
        payout.status = "unclaimed"
        payout.failure_reason = (
            f"{payout.receiver_email} has no PayPal account yet. PayPal returns unclaimed "
            "payouts after 30 days."
        )
        note(session, contract, f"Payout unclaimed: {payout.failure_reason}", actor=PAYPAL)
    elif status == "returned":
        payout.status = "returned"
        payout.failure_reason = item.error or "PayPal returned the payout."
        note(session, contract, f"Payout returned: {payout.failure_reason}", actor=PAYPAL)
    else:
        fail(session, contract, payout, item.error or "PayPal couldn't complete the payout.")
    return True
