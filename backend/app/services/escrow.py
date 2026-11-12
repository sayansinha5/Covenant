"""Escrow bookkeeping: agreeing to a contract (budget reserved under the organization lock),
planning the settlement, and the state, ledger and payout writes the PayPal jobs share."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError, ConflictError
from app.core.ids import uuid7
from app.core.money import CENT
from app.db.base import utcnow
from app.domain.policy import Outcome, PolicyDecision, evaluate, month_start, usd
from app.domain.settlement import Band, Settlement, settle
from app.domain.state_machine import TERMINAL_STATES, Event, Job, Ledger, State
from app.integrations.paypal import PayPalClient
from app.integrations.paypal.payouts import payout_sender_batch_id
from app.integrations.paypal.types import Authorization
from app.models import Approval, Contract, Escrow, Organization, Payout
from app.services import ledger
from app.services.contracts import (
    Actor,
    ContractNotFound,
    lock_contract,
    note,
    transition,
)
from app.services.funding import FundingService
from app.services.mandates import active_mandate, terms_of
from app.services.outbox import enqueue

PAYPAL = Actor("paypal")
HOLD_DECLINED = "PayPal declined the hold. Reconnect PayPal in Settings."
# Where PayPal sends the payer after approving a hold in approve_each mode.
ORDER_RETURN_PATH = "/api/v1/paypal/orders/return"


class ApprovalRequired(ConflictError):
    code = "APPROVAL_REQUIRED"


class PolicyRejected(AppError):
    status = 422
    title = "Outside the mandate"

    def __init__(self, decision: PolicyDecision) -> None:
        super().__init__(decision.reason, code=decision.code)


async def lock_org(session: AsyncSession, org_id: str) -> Organization:
    """Serializes funding (and mandate signing) per organization."""
    return (
        await session.scalars(
            select(Organization).where(Organization.id == org_id).with_for_update()
        )
    ).one()


async def lock_for_paypal(
    session: AsyncSession, contract_id: str
) -> tuple[Contract, Escrow | None] | None:
    """Lock organization, contract and escrow (the order every funding path uses) before
    applying something PayPal reported. None if there's no such contract."""
    contract = await session.get(Contract, contract_id)
    if contract is None:
        return None
    await lock_org(session, contract.hirer_org_id)
    contract = await lock_contract(session, contract_id)
    return contract, await locked_escrow(session, contract_id)


def planned_void(escrow: Escrow) -> bool:
    return escrow.settlement is not None and Decimal(escrow.settlement["captured"]) == 0


async def locked_escrow(session: AsyncSession, contract_id: str) -> Escrow | None:
    return await session.scalar(
        select(Escrow)
        .where(Escrow.contract_id == contract_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


async def committed_this_month(
    session: AsyncSession, org_id: str, now: datetime, *, excluding_contract_id: str
) -> Decimal:
    """Held + captured for holds reserved this calendar month (UTC); released money doesn't
    count. Holds still being created count too, so concurrent funding can't overshoot."""
    total = await session.scalar(
        select(func.coalesce(func.sum(Escrow.amount - Escrow.amount_released), 0)).where(
            Escrow.org_id == org_id,
            Escrow.status != "failed",
            Escrow.reserved_at >= month_start(now),
            Escrow.contract_id != excluding_contract_id,
        )
    )
    return Decimal(total or 0).quantize(CENT)


async def check_policy(
    session: AsyncSession, settings: Settings, paypal: PayPalClient, contract: Contract
) -> tuple[PolicyDecision, str | None]:
    """Evaluate the hirer's active mandate for this contract. Call with the org row locked."""
    mandate = await active_mandate(session, contract.hirer_org_id)
    approved = await session.scalar(
        select(func.count())
        .select_from(Approval)
        .where(Approval.contract_id == contract.id, Approval.status == "approved")
    )
    decision = evaluate(
        terms_of(mandate),
        amount=contract.amount,
        work_type=contract.work_type,
        committed_this_month=await committed_this_month(
            session, contract.hirer_org_id, utcnow(), excluding_contract_id=contract.id
        ),
        funding_connected=await FundingService(session, settings, paypal).is_connected(
            contract.hirer_org_id
        ),
        approved=bool(approved),
    )
    return decision, mandate.id if mandate else None


async def agree(
    session: AsyncSession,
    settings: Settings,
    paypal: PayPalClient,
    *,
    org_id: str,
    contract_id: str,
    actor: Actor,
    actor_name: str,
) -> tuple[Contract, PolicyDecision]:
    """The hirer agrees: check the mandate, reserve the amount and enqueue the hold."""
    await lock_org(session, org_id)
    contract = await lock_contract(session, contract_id)
    if contract.hirer_org_id != org_id:
        raise ContractNotFound
    if contract.state != State.AWAITING_AGREEMENT:
        raise ConflictError(
            "This contract isn't waiting for your agreement.", code="INVALID_TRANSITION"
        )

    decision, mandate_id = await check_policy(session, settings, paypal, contract)
    if decision.outcome is Outcome.NEEDS_APPROVAL:
        raise ApprovalRequired(decision.reason)
    if not decision.allowed:
        raise PolicyRejected(decision)

    escrow = await locked_escrow(session, contract.id)
    if escrow is None:
        escrow = Escrow(id=uuid7(), contract_id=contract.id, org_id=org_id, request_series=1)
        session.add(escrow)
    else:
        # A new hold after a definite failure gets new PayPal request IDs.
        escrow.request_series += 1
    escrow.status = "pending"
    escrow.amount = contract.amount
    escrow.currency = contract.currency
    escrow.reserved_at = utcnow()
    escrow.failure_reason = None
    escrow.paypal_order_id = escrow.paypal_authorization_id = escrow.payer_action_url = None
    contract.mandate_id = mandate_id
    if contract.spec and not contract.spec_hash:
        from app.ai.spec_writer.spec import fingerprint

        contract.spec_hash = fingerprint(contract.spec)

    await transition(
        session,
        contract,
        Event.HIRER_AGREED,
        actor=actor,
        message=f"{actor_name} agreed to {usd(contract.amount)}. Asking PayPal to hold it.",
        data={"mandate_version": decision.mandate_version},
    )
    return contract, decision


async def cancel(
    session: AsyncSession, *, org_id: str, contract_id: str, actor: Actor, actor_name: str
) -> Contract:
    """The hirer cancels before the worker accepts; a hold, if any, is voided."""
    contract = await lock_contract(session, contract_id)
    if contract.hirer_org_id != org_id:
        raise ContractNotFound
    state = State(contract.state)
    if state is State.AWAITING_AGREEMENT:
        event, message = Event.HIRER_DECLINED, f"{actor_name} declined the contract."
    elif state in (State.FUNDED, State.SENT_TO_WORKER):
        event = Event.HIRER_CANCELLED
        message = f"{actor_name} cancelled the contract. Releasing the hold."
    elif state is State.FUNDING:
        raise ConflictError(
            "We're confirming the hold with PayPal. Try again in a moment.",
            code="HOLD_IN_PROGRESS",
        )
    else:
        raise ConflictError(
            "This contract can't be cancelled any more: the worker has already started.",
            code="INVALID_TRANSITION",
        )
    await transition(session, contract, event, actor=actor, message=message)
    return contract


async def begin_settlement(
    session: AsyncSession,
    settings: Settings,
    contract: Contract,
    event: Event,
    band: Band,
    *,
    pass_ratio: Decimal,
    actor: Actor,
    message: str,
) -> Settlement:
    """Move a locked contract into `settling` with amounts from the settlement engine, and
    enqueue the one capture or void that carries them out."""
    escrow = await locked_escrow(session, contract.id)
    if escrow is None or escrow.status != "held":
        raise ConflictError("There's no PayPal hold to settle.", code="NO_HOLD")
    plan = settle(
        escrow.amount_held, band, pass_ratio=pass_ratio, fee_rate=settings.platform_fee_rate
    )
    escrow.settlement = {
        "band": band.value,
        "pass_ratio": str(pass_ratio),
        "captured": str(plan.captured),
        "released": str(plan.released),
        "fee": str(plan.fee),
        "payout": str(plan.payout),
    }
    await transition(session, contract, event, actor=actor, message=message, data=escrow.settlement)
    job = Job.VOID if plan.is_void else Job.CAPTURE
    await enqueue(session, job, {"contract_id": contract.id}, dedupe_key=f"{job}:{contract.id}")
    return plan


async def payer_returned(session: AsyncSession, *, order_id: str, cancelled: bool) -> str | None:
    """The payer came back from PayPal's approval page (approve_each mode). Approval queues the
    authorization; cancelling releases the reservation. Returns the contract ID, if any."""
    contract_id = await session.scalar(
        select(Escrow.contract_id).where(
            Escrow.paypal_order_id == order_id, Escrow.status == "payer_action"
        )
    )
    if contract_id is None:
        return None
    contract = await session.get_one(Contract, contract_id)
    await lock_org(session, contract.hirer_org_id)
    contract = await lock_contract(session, contract_id)
    escrow = await locked_escrow(session, contract_id)
    if escrow is None or escrow.status != "payer_action" or contract.state != State.FUNDING:
        return contract_id
    if cancelled:
        await fail_hold(
            session, contract, escrow, "PayPal approval was cancelled. Nothing was held."
        )
    else:
        await enqueue(
            session,
            Job.CREATE_HOLD,
            {"contract_id": contract_id},
            dedupe_key=f"{Job.CREATE_HOLD}:{contract_id}:approved:{order_id}",
        )
    return contract_id


def paypal_time(value: datetime | None) -> datetime | None:
    """PayPal timestamps are zone-aware; columns store naive UTC."""
    return value.astimezone(UTC).replace(tzinfo=None) if value else None


async def mark_inconsistent(
    session: AsyncSession, contract: Contract, message: str, *, data: dict[str, Any] | None = None
) -> None:
    """PayPal disagrees with us: park an open contract in `needs_attention` for an admin, or
    just note it on a contract that has already finished."""
    state = State(contract.state)
    if state in TERMINAL_STATES or state is State.NEEDS_ATTENTION:
        note(session, contract, message, actor=PAYPAL, data=data)
        return
    await transition(
        session, contract, Event.PAYPAL_INCONSISTENT, actor=PAYPAL, message=message, data=data
    )


async def record_hold(
    session: AsyncSession,
    settings: Settings,
    contract: Contract,
    escrow: Escrow,
    authorization: Authorization,
) -> None:
    now = utcnow()
    escrow.status = "held"
    escrow.paypal_authorization_id = authorization.id
    escrow.amount_held = authorization.amount
    escrow.honor_period_ends_at = now + timedelta(days=settings.auth_honor_period_days)
    escrow.auth_expires_at = paypal_time(authorization.expiration_time)
    ledger.record(
        session,
        org_id=contract.hirer_org_id,
        contract=contract,
        direction=Ledger.HELD,
        amount=authorization.amount,
        actor=PAYPAL,
        paypal_reference=authorization.id,
    )
    await transition(
        session,
        contract,
        Event.HOLD_CONFIRMED,
        actor=PAYPAL,
        message=f"PayPal is holding {usd(authorization.amount)}.",
        data={"authorization_id": authorization.id},
    )


async def fail_hold(
    session: AsyncSession,
    contract: Contract,
    escrow: Escrow,
    reason: str,
    *,
    data: dict[str, Any] | None = None,
) -> None:
    """Nothing is held: release the reservation and return the contract to the hirer."""
    escrow.status = "failed"
    escrow.failure_reason = reason
    await transition(session, contract, Event.HOLD_FAILED, actor=PAYPAL, message=reason, data=data)


async def record_capture(
    session: AsyncSession, contract: Contract, escrow: Escrow, *, capture_id: str, amount: Decimal
) -> None:
    """Book a completed capture: ledger, payout row and the settled transition."""
    if escrow.settlement is None:
        raise ValueError("A capture needs a planned settlement")
    fee = Decimal(escrow.settlement["fee"])
    net = Decimal(escrow.settlement["payout"])
    released = escrow.amount_held - amount
    escrow.status = "captured"
    escrow.paypal_capture_id = capture_id
    escrow.amount_captured = amount
    escrow.amount_released = released

    hirer, provider = contract.hirer_org_id, contract.provider_org_id
    for org_id, direction, value in (
        (hirer, Ledger.CAPTURED, amount),
        (hirer, Ledger.RELEASED, released),
        (provider, Ledger.FEE, fee),
    ):
        ledger.record(
            session,
            org_id=org_id,
            contract=contract,
            direction=direction,
            amount=value,
            actor=PAYPAL,
            paypal_reference=capture_id,
        )

    if net > 0:
        provider_org = await session.get_one(Organization, provider)
        payout_id = uuid7()
        session.add(
            Payout(
                id=payout_id,
                contract_id=contract.id,
                provider_org_id=provider,
                receiver_email=provider_org.payout_email,
                gross=amount,
                fee=fee,
                net=net,
                currency=contract.currency,
                sender_batch_id=payout_sender_batch_id(payout_id),
            )
        )

    full = released == 0
    await transition(
        session,
        contract,
        Event.CAPTURED_FULL if full else Event.CAPTURED_PARTIAL,
        actor=PAYPAL,
        message=(
            f"PayPal captured {usd(amount)}."
            if full
            else f"PayPal captured {usd(amount)} and released {usd(released)} to the hirer."
        ),
        data={"capture_id": capture_id},
    )


async def record_void(session: AsyncSession, contract: Contract, escrow: Escrow) -> None:
    released = escrow.amount_held - escrow.amount_captured
    escrow.status = "voided"
    escrow.amount_released = escrow.amount_held
    ledger.record(
        session,
        org_id=contract.hirer_org_id,
        contract=contract,
        direction=Ledger.RELEASED,
        amount=released,
        actor=PAYPAL,
        paypal_reference=escrow.paypal_authorization_id,
    )
    message = f"PayPal released the {usd(released)} hold."
    if contract.state == State.SETTLING and planned_void(escrow):
        await transition(session, contract, Event.VOIDED, actor=PAYPAL, message=message)
    else:
        note(session, contract, message, actor=PAYPAL)
