"""`escrow.reauthorize_scan` (every 30 minutes) finds holds past PayPal's 3-day honour period
on contracts still in progress; `escrow.reauthorize` renews each one once."""

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.domain.state_machine import Job
from app.integrations.paypal import PayPalApiError
from app.integrations.paypal.audit import Operation, operation_request_id
from app.jobs.base import JobContext, JobHandler, Payload
from app.models import Contract, Escrow
from app.services import escrow as escrows
from app.services.contracts import lock_contract, note
from app.services.outbox import enqueue
from app.services.paypal_sync import WORK_STATES

SCAN_INTERVAL = timedelta(minutes=30)


async def scan(session: AsyncSession, ctx: JobContext, payload: Payload) -> None:
    rows = await session.execute(
        select(Escrow.contract_id, Escrow.request_series)
        .join(Contract, Contract.id == Escrow.contract_id)
        .where(
            Escrow.status == "held",
            Escrow.reauthorized_at.is_(None),
            Escrow.honor_period_ends_at <= utcnow(),
            Contract.state.in_(WORK_STATES),
        )
    )
    for contract_id, series in rows:
        await enqueue(
            session,
            Job.REAUTHORIZE,
            {"contract_id": contract_id},
            dedupe_key=f"{Job.REAUTHORIZE}:{contract_id}:{series}",
        )


async def run(session: AsyncSession, ctx: JobContext, payload: Payload) -> None:
    contract = await lock_contract(session, payload["contract_id"])
    escrow = await escrows.locked_escrow(session, contract.id)
    now = utcnow()
    if (
        escrow is None
        or escrow.status != "held"
        or escrow.reauthorized_at is not None
        or escrow.paypal_authorization_id is None
        or contract.state not in WORK_STATES
    ):
        return
    try:
        authorization = await ctx.paypal.reauthorize_authorization(
            escrow.paypal_authorization_id,
            operation=Operation(
                kind="reauthorize",
                request_id=operation_request_id(contract.id, "reauthorize", escrow.request_series),
                contract_id=contract.id,
            ),
            amount=escrow.amount_held,
        )
    except PayPalApiError as exc:
        if exc.retryable:
            raise
        await escrows.mark_inconsistent(
            session,
            contract,
            f"PayPal wouldn't renew the hold: {exc.message or exc.name}",
            data={"paypal_error": exc.name, "paypal_debug_id": exc.debug_id},
        )
        return
    previous = escrow.paypal_authorization_id
    escrow.paypal_authorization_id = authorization.id
    escrow.reauthorized_at = now
    escrow.honor_period_ends_at = now + timedelta(days=ctx.settings.auth_honor_period_days)
    escrow.auth_expires_at = escrows.paypal_time(authorization.expiration_time)
    note(
        session,
        contract,
        "PayPal renewed the hold so the money stays reserved while the work finishes.",
        actor=escrows.PAYPAL,
        data={"previous_authorization_id": previous, "authorization_id": authorization.id},
    )


async def give_up(session: AsyncSession, ctx: JobContext, payload: Payload, error: str) -> None:
    contract = await lock_contract(session, payload["contract_id"])
    await escrows.mark_inconsistent(
        session,
        contract,
        "We couldn't renew the PayPal hold. An admin will check it.",
        data={"error": error},
    )


SCAN_HANDLER = JobHandler(run=scan)
HANDLER = JobHandler(run=run, on_give_up=give_up)
