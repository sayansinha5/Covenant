"""`escrow.void`: release the whole hold (fail, manipulation, cancellation, expiry). Voiding an
authorization PayPal already voided or expired counts as success."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.paypal import PayPalApiError
from app.integrations.paypal.audit import Operation, operation_request_id
from app.jobs.base import JobContext, JobHandler, Payload
from app.services import escrow as escrows
from app.services.contracts import lock_contract


async def run(session: AsyncSession, ctx: JobContext, payload: Payload) -> None:
    contract = await lock_contract(session, payload["contract_id"])
    escrow = await escrows.locked_escrow(session, contract.id)
    if escrow is None or escrow.status != "held" or escrow.paypal_authorization_id is None:
        return
    try:
        authorization = await ctx.paypal.void_authorization(
            escrow.paypal_authorization_id,
            operation=Operation(
                kind="void",
                request_id=operation_request_id(contract.id, "void", escrow.request_series),
                contract_id=contract.id,
            ),
        )
    except PayPalApiError as exc:
        if exc.retryable:
            raise
        await escrows.mark_inconsistent(
            session,
            contract,
            f"PayPal refused to release the hold: {exc.message or exc.name}",
            data={"paypal_error": exc.name, "paypal_debug_id": exc.debug_id},
        )
        return
    if authorization.status in ("VOIDED", "EXPIRED"):
        await escrows.record_void(session, contract, escrow)
    else:
        await escrows.mark_inconsistent(
            session,
            contract,
            f"PayPal reported the hold as {authorization.status} after releasing it.",
        )


async def give_up(session: AsyncSession, ctx: JobContext, payload: Payload, error: str) -> None:
    contract = await lock_contract(session, payload["contract_id"])
    await escrows.mark_inconsistent(
        session,
        contract,
        "We couldn't confirm with PayPal that the hold was released. An admin will check it.",
        data={"error": error},
    )


HANDLER = JobHandler(run=run, on_give_up=give_up)
