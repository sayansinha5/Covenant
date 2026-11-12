"""`escrow.capture`: capture the amount the settlement engine planned, with final_capture so
PayPal releases the rest of the hold."""

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.state_machine import State
from app.integrations.paypal import PayPalApiError
from app.integrations.paypal.audit import Operation, operation_request_id
from app.jobs.base import JobContext, JobHandler, Payload
from app.services import escrow as escrows
from app.services.contracts import lock_contract, note


async def run(session: AsyncSession, ctx: JobContext, payload: Payload) -> None:
    contract = await lock_contract(session, payload["contract_id"])
    escrow = await escrows.locked_escrow(session, contract.id)
    if contract.state != State.SETTLING or escrow is None or escrow.status != "held":
        return
    if escrow.settlement is None or escrow.paypal_authorization_id is None:
        raise ValueError(f"Contract {contract.id} is settling without a planned capture")

    amount = Decimal(escrow.settlement["captured"])
    try:
        capture = await ctx.paypal.capture_authorization(
            escrow.paypal_authorization_id,
            operation=Operation(
                kind="capture",
                request_id=operation_request_id(contract.id, "capture", escrow.request_series),
                contract_id=contract.id,
            ),
            amount=amount,
            invoice_id=f"C-{contract.number}",
            note_to_payer=f"Covenant C-{contract.number}: {contract.title}",
        )
    except PayPalApiError as exc:
        if exc.retryable:
            raise
        await escrows.mark_inconsistent(
            session,
            contract,
            f"PayPal refused the capture: {exc.message or exc.name}",
            data={"paypal_error": exc.name, "paypal_debug_id": exc.debug_id},
        )
        return

    if capture.status == "COMPLETED" and capture.amount == amount:
        await escrows.record_capture(
            session, contract, escrow, capture_id=capture.id, amount=capture.amount
        )
    elif capture.status == "PENDING":
        # PAYMENT.CAPTURE.COMPLETED (webhook) or reconciliation books it.
        escrow.status = "capture_pending"
        escrow.paypal_capture_id = capture.id
        note(
            session,
            contract,
            "PayPal is still processing the capture.",
            actor=escrows.PAYPAL,
            data={"capture_id": capture.id},
        )
    else:
        await escrows.mark_inconsistent(
            session,
            contract,
            f"PayPal reported the capture as {capture.status} for {capture.amount}.",
            data={"capture_id": capture.id},
        )


async def give_up(session: AsyncSession, ctx: JobContext, payload: Payload, error: str) -> None:
    contract = await lock_contract(session, payload["contract_id"])
    await escrows.mark_inconsistent(
        session,
        contract,
        "We couldn't confirm the capture with PayPal. An admin will check it.",
        data={"error": error},
    )


HANDLER = JobHandler(run=run, on_give_up=give_up)
