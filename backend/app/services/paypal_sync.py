"""Bringing our records in line with what PayPal reports. Webhooks and reconciliation share
these, so both safety nets reach the same conclusion. Callers pass rows already locked
(organization, contract, escrow) and get back what happened."""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.domain.policy import usd
from app.domain.state_machine import State
from app.integrations.paypal.types import Authorization, Capture, PayoutItem
from app.models import Contract, Escrow, Payout
from app.services import escrow as escrows
from app.services import payouts

# Work is under way in these states, so the money must still be held.
WORK_STATES = (
    State.FUNDED,
    State.SENT_TO_WORKER,
    State.IN_PROGRESS,
    State.VERIFYING,
    State.VERDICT_ISSUED,
    State.UNDER_APPEAL,
)
# Contracts that ended before settling; their hold is being released.
RELEASING_STATES = (State.CANCELLED, State.EXPIRED)
RELEASED = ("VOIDED", "EXPIRED")


class Result(StrEnum):
    IN_SYNC = "in_sync"
    FIXED = "fixed"
    NEEDS_ATTENTION = "needs_attention"
    IGNORED = "ignored"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class Sync:
    result: Result
    message: str


def in_sync(message: str) -> Sync:
    return Sync(Result.IN_SYNC, message)


def ignored(message: str) -> Sync:
    return Sync(Result.IGNORED, message)


async def flag(session: AsyncSession, contract: Contract, message: str) -> Sync:
    await escrows.mark_inconsistent(session, contract, message)
    return Sync(Result.NEEDS_ATTENTION, message)


async def hold_authorized(
    session: AsyncSession,
    settings: Settings,
    contract: Contract,
    escrow: Escrow,
    authorization: Authorization,
) -> Sync:
    """A contract in `funding`: PayPal reports the hold's authorization."""
    if contract.state != State.FUNDING or escrow.status not in ("pending", "payer_action"):
        return ignored("The hold was already recorded.")
    if authorization.status == "CREATED":
        if authorization.amount != escrow.amount:
            return await flag(
                session,
                contract,
                f"PayPal is holding {usd(authorization.amount)} but the contract is for "
                f"{usd(escrow.amount)}.",
            )
        await escrows.record_hold(session, settings, contract, escrow, authorization)
        return Sync(
            Result.FIXED, f"Recorded the {usd(authorization.amount)} hold PayPal confirmed."
        )
    if authorization.status == "PENDING":
        escrow.paypal_authorization_id = authorization.id
        return in_sync("PayPal is still reviewing the hold.")
    if authorization.status in (*RELEASED, "DENIED"):
        await escrows.fail_hold(session, contract, escrow, escrows.HOLD_DECLINED)
        return Sync(
            Result.FIXED, "PayPal didn't hold the money; the contract is back with the hirer."
        )
    return await flag(session, contract, f"PayPal reports the new hold as {authorization.status}.")


async def hold_released(
    session: AsyncSession, contract: Contract, escrow: Escrow, paypal_status: str
) -> Sync:
    """PayPal says a held authorization was voided or has expired."""
    if escrow.status != "held":
        return ignored("The release was already recorded.")
    expected = contract.state in RELEASING_STATES or (
        contract.state == State.SETTLING and escrows.planned_void(escrow)
    )
    await escrows.record_void(session, contract, escrow)
    if expected:
        return Sync(Result.FIXED, "Recorded PayPal's release of the hold.")
    return await flag(
        session,
        contract,
        f"PayPal reports the hold as {paypal_status} while the contract is "
        f"{contract.state.replace('_', ' ')}. The worker should stop.",
    )


async def capture_reported(
    session: AsyncSession, contract: Contract, escrow: Escrow, capture: Capture
) -> Sync:
    """A contract in `settling` with a planned capture: PayPal reports the capture."""
    if (
        contract.state != State.SETTLING
        or escrow.status not in ("held", "capture_pending")
        or escrows.planned_void(escrow)
        or escrow.settlement is None
    ):
        return ignored("The capture was already recorded.")
    planned = Decimal(escrow.settlement["captured"])
    if capture.status == "COMPLETED":
        if capture.amount != planned:
            return await flag(
                session,
                contract,
                f"PayPal captured {usd(capture.amount)} but the settlement was {usd(planned)}.",
            )
        await escrows.record_capture(
            session, contract, escrow, capture_id=capture.id, amount=capture.amount
        )
        return Sync(Result.FIXED, f"Recorded the {usd(capture.amount)} capture PayPal completed.")
    if capture.status == "PENDING":
        escrow.status = "capture_pending"
        escrow.paypal_capture_id = capture.id
        return in_sync("PayPal is still processing the capture.")
    return await flag(session, contract, f"PayPal reports the capture as {capture.status}.")


def payout_item_reported(
    session: AsyncSession,
    contract: Contract,
    payout: Payout,
    item: PayoutItem,
    status: str | None,
) -> Sync:
    """PayPal reports a payout item. `status` is ours (see FINAL_ITEM_STATUSES), None while
    PayPal is still working on it."""
    if status is None:
        return in_sync("PayPal is still processing the payout.")
    if payouts.apply_item_status(session, contract, payout, item, status):
        return Sync(Result.FIXED, f"Payout is now {status}.")
    return in_sync(f"Payout is already {payout.status}.")
