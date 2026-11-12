"""Reconciliation: compare every open hold and recent open payout with PayPal, apply what is
safe (the same rules webhooks use) and flag the rest as `needs_attention`. Runs every 5
minutes and on demand from Admin; each run leaves a summary row."""

from collections import Counter
from collections.abc import Awaitable, Callable, Sequence
from datetime import timedelta
from typing import Any

from sqlalchemy import Select, and_, delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.logging import get_logger
from app.db.base import utcnow
from app.db.engine import Database
from app.domain.state_machine import TERMINAL_STATES, Job, State
from app.integrations.paypal import PayPalClient, PayPalError
from app.models import Contract, Escrow, Payout, ReconciliationRun
from app.services import escrow as escrows
from app.services import payouts
from app.services.outbox import enqueue
from app.services.paypal_sync import (
    RELEASED,
    RELEASING_STATES,
    Result,
    Sync,
    capture_reported,
    flag,
    hold_authorized,
    hold_released,
    in_sync,
    payout_item_reported,
)

logger = get_logger("covenant.reconcile")

INTERVAL = timedelta(minutes=5)
PAYOUT_WINDOW = timedelta(days=30)
KEEP_RUNS = timedelta(days=7)
STALE_RUN = timedelta(minutes=15)
OPEN_ESCROW = ("pending", "payer_action", "held", "capture_pending")
# Orders that are still waiting for the payer (approve_each mode).
AWAITING_PAYER = ("CREATED", "SAVED", "APPROVED", "PAYER_ACTION_REQUIRED")


async def request(session: AsyncSession, *, requested_by: str) -> ReconciliationRun:
    """Queue an on-demand run, or return a recent one that is still queued or running."""
    active = await session.scalar(
        select(ReconciliationRun)
        .where(
            ReconciliationRun.status.in_(("queued", "running")),
            # A run whose runner died stays "running"; don't let it block new runs forever.
            ReconciliationRun.created_at >= utcnow() - STALE_RUN,
        )
        .order_by(ReconciliationRun.created_at.desc())
        .limit(1)
    )
    if active is not None:
        return active
    run = ReconciliationRun(trigger="admin", requested_by=requested_by)
    session.add(run)
    await session.flush()
    await enqueue(
        session, Job.RECONCILE, {"run_id": run.id}, dedupe_key=f"{Job.RECONCILE}:{run.id}"
    )
    return run


async def last_run(session: AsyncSession) -> ReconciliationRun | None:
    return await session.scalar(
        select(ReconciliationRun).order_by(ReconciliationRun.created_at.desc()).limit(1)
    )


async def run(
    database: Database, settings: Settings, paypal: PayPalClient, run_id: str | None
) -> str | None:
    """Do one reconciliation pass; scheduled passes (no run_id) create their own row.
    Each contract and payout is checked in its own transaction. Returns the run ID."""
    async with database.session() as session, session.begin():
        if run_id is None:
            summary = ReconciliationRun(trigger="schedule")
            session.add(summary)
        else:
            found = await session.get(ReconciliationRun, run_id, with_for_update=True)
            if found is None or found.status == "done":
                return None
            summary = found
        summary.status = "running"
        summary.started_at = utcnow()
        await session.flush()
        run_id = summary.id
        holds = (await session.execute(_open_holds())).all()
        open_payouts = (await session.execute(_open_payouts())).all()

    tally: Counter[Result] = Counter()
    findings: list[dict[str, Any]] = []
    checks: tuple[tuple[str, Sequence[tuple[str, str, int]], Check], ...] = (
        ("hold", holds, _check_contract),
        ("payout", open_payouts, _check_payout),
    )
    for subject, rows, check in checks:
        for item_id, contract_id, number in rows:
            try:
                async with database.session() as session, session.begin():
                    outcome = await check(session, settings, paypal, item_id)
            except PayPalError as exc:
                outcome = Sync(Result.ERROR, f"Couldn't read PayPal's records: {exc}")
            tally[outcome.result] += 1
            if outcome.result not in (Result.IN_SYNC, Result.IGNORED):
                findings.append(
                    {
                        "subject": subject,
                        "contract_id": contract_id,
                        "contract_number": f"C-{number}",
                        "result": outcome.result.value,
                        "message": outcome.message,
                    }
                )
    checked = len(holds) + len(open_payouts)

    async with database.session() as session, session.begin():
        summary = await session.get_one(ReconciliationRun, run_id)
        summary.status = "done"
        summary.finished_at = utcnow()
        summary.checked = checked
        summary.in_sync = tally[Result.IN_SYNC] + tally[Result.IGNORED]
        summary.fixed = tally[Result.FIXED]
        summary.needs_attention = tally[Result.NEEDS_ATTENTION]
        summary.errors = tally[Result.ERROR]
        summary.findings = findings
        await session.execute(
            delete(ReconciliationRun).where(ReconciliationRun.created_at < utcnow() - KEEP_RUNS)
        )
    logger.info(
        "reconcile_done",
        run_id=run_id,
        checked=checked,
        fixed=tally[Result.FIXED],
        needs_attention=tally[Result.NEEDS_ATTENTION],
        errors=tally[Result.ERROR],
    )
    return run_id


async def mark_failed(session: AsyncSession, run_id: str | None, error: str) -> None:
    if run_id is None:
        return
    summary = await session.get(ReconciliationRun, run_id)
    if summary is not None and summary.status != "done":
        summary.status = "failed"
        summary.finished_at = utcnow()
        summary.findings = [{"subject": "run", "result": "error", "message": error[:500]}]


def _open_holds() -> Select[str, str, int]:
    open_contract = and_(
        Contract.state.notin_([*TERMINAL_STATES, State.NEEDS_ATTENTION]),
        Escrow.status.in_(OPEN_ESCROW),
        or_(Escrow.paypal_authorization_id.isnot(None), Escrow.paypal_order_id.isnot(None)),
    )
    being_released = and_(Contract.state.in_(RELEASING_STATES), Escrow.status == "held")
    return (
        select(Contract.id, Contract.id.label("contract_id"), Contract.number)
        .join(Escrow, Escrow.contract_id == Contract.id)
        .where(or_(open_contract, being_released))
        .order_by(Contract.number)
    )


def _open_payouts() -> Select[str, str, int]:
    return (
        select(Payout.id, Contract.id, Contract.number)
        .join(Contract, Contract.id == Payout.contract_id)
        .where(
            Payout.status.in_(payouts.OPEN_STATUSES),
            Payout.paypal_batch_id.isnot(None),
            Payout.created_at >= utcnow() - PAYOUT_WINDOW,
        )
        .order_by(Payout.created_at)
    )


Check = Callable[[AsyncSession, Settings, PayPalClient, str], Awaitable[Sync]]


async def _check_contract(
    session: AsyncSession, settings: Settings, paypal: PayPalClient, contract_id: str
) -> Sync:
    locked = await escrows.lock_for_paypal(session, contract_id)
    if locked is None:
        return in_sync("No such contract.")
    contract, escrow = locked
    if escrow is None:
        return in_sync("No PayPal hold.")
    state = State(contract.state)

    if state is State.FUNDING:
        if escrow.status not in ("pending", "payer_action"):
            return in_sync("The hold is recorded.")
        if escrow.paypal_authorization_id:
            authorization = await paypal.get_authorization(escrow.paypal_authorization_id)
        elif escrow.paypal_order_id:
            order = await paypal.get_order(escrow.paypal_order_id)
            if order.authorization is None:
                if order.status in AWAITING_PAYER:
                    return in_sync("Waiting for the payer to approve in PayPal.")
                await escrows.fail_hold(session, contract, escrow, escrows.HOLD_DECLINED)
                return Sync(Result.FIXED, f"PayPal reports the order as {order.status}.")
            authorization = order.authorization
        else:
            return in_sync("The hold request hasn't reached PayPal yet.")
        return await hold_authorized(session, settings, contract, escrow, authorization)

    if escrow.status not in ("held", "capture_pending"):
        return in_sync(f"The hold is {escrow.status}.")
    if escrow.paypal_authorization_id is None:
        return await flag(session, contract, "The hold has no PayPal authorization.")
    authorization = await paypal.get_authorization(escrow.paypal_authorization_id)

    if state is State.SETTLING and not escrows.planned_void(escrow):
        if escrow.paypal_order_id is None:
            return await flag(session, contract, "The hold has no PayPal order.")
        order = await paypal.get_order(escrow.paypal_order_id)
        captures = [c for c in order.captures if c.status in ("COMPLETED", "PENDING")]
        if captures:
            completed = [c for c in captures if c.status == "COMPLETED"]
            return await capture_reported(session, contract, escrow, (completed or captures)[-1])
        if authorization.status == "CREATED":
            return in_sync("Waiting for the capture job.")
    if authorization.status in RELEASED:
        return await hold_released(session, contract, escrow, authorization.status)
    if authorization.status in ("CREATED", "PENDING"):
        releasing = state is State.SETTLING or state in RELEASING_STATES
        return in_sync(
            "Waiting for the release job." if releasing else "PayPal is holding the money."
        )
    return await flag(session, contract, f"PayPal reports the hold as {authorization.status}.")


async def _check_payout(
    session: AsyncSession, settings: Settings, paypal: PayPalClient, payout_id: str
) -> Sync:
    contract_id = await session.scalar(select(Payout.contract_id).where(Payout.id == payout_id))
    payout = await payouts.locked_payout(session, contract_id) if contract_id else None
    if payout is None or payout.paypal_batch_id is None:
        return in_sync("No PayPal payout.")
    if payout.status not in payouts.OPEN_STATUSES:
        return in_sync(f"Payout is {payout.status}.")
    contract = await session.get_one(Contract, payout.contract_id)
    batch = await paypal.get_payout_batch(payout.paypal_batch_id)
    if batch.batch_status == "DENIED":
        payouts.fail(session, contract, payout, "PayPal denied the payout batch.")
        return Sync(Result.FIXED, "Payout failed: PayPal denied the batch.")
    if not batch.items:
        return in_sync("PayPal is still processing the payout.")
    item = batch.items[0]
    status = payouts.FINAL_ITEM_STATUSES.get(item.transaction_status)
    return payout_item_reported(session, contract, payout, item, status)
