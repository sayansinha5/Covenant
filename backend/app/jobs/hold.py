"""`escrow.create_hold`: re-check the mandate under the organization lock, then ask PayPal to
authorize the contract amount (vault: no payer interaction; approve_each: the payer approves
in a PayPal window first, then this job runs again to authorize)."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.domain.state_machine import State
from app.integrations.paypal import PayPalApiError, PayPalNotConfigured
from app.integrations.paypal.audit import Operation, OperationKind, operation_request_id
from app.integrations.paypal.types import Order
from app.jobs.base import JobContext, JobHandler, Payload
from app.models import Contract, Escrow
from app.services import escrow as escrows
from app.services.contracts import lock_contract, note
from app.services.funding import FundingService

logger = get_logger("covenant.jobs.hold")


async def _locked(session: AsyncSession, contract_id: str) -> tuple[Contract, Escrow] | None:
    locked = await escrows.lock_for_paypal(session, contract_id)
    if locked is None:
        return None
    contract, escrow = locked
    if contract.state != State.FUNDING or escrow is None:
        return None
    return contract, escrow


def _operation(contract: Contract, escrow: Escrow, kind: OperationKind) -> Operation:
    return Operation(
        kind=kind,
        request_id=operation_request_id(contract.id, kind, escrow.request_series),
        contract_id=contract.id,
    )


async def run(session: AsyncSession, ctx: JobContext, payload: Payload) -> None:
    locked = await _locked(session, payload["contract_id"])
    if locked is None:
        return
    contract, escrow = locked
    if escrow.status not in ("pending", "payer_action"):
        return

    decision, _ = await escrows.check_policy(session, ctx.settings, ctx.paypal, contract)
    if not decision.allowed:
        await escrows.fail_hold(session, contract, escrow, decision.reason)
        return

    try:
        order = await _authorized_order(session, ctx, contract, escrow)
    except PayPalNotConfigured:
        await escrows.fail_hold(
            session, contract, escrow, "PayPal isn't configured on this server. Nothing was held."
        )
        return
    except PayPalApiError as exc:
        if exc.retryable:
            raise
        logger.warning("hold_declined", contract_id=contract.id, error=str(exc))
        await escrows.fail_hold(
            session,
            contract,
            escrow,
            escrows.HOLD_DECLINED,
            data={"paypal_error": exc.name, "paypal_debug_id": exc.debug_id},
        )
        return
    if order is None:
        return

    authorization = order.authorization
    if authorization is None or authorization.status in ("DENIED", "VOIDED", "EXPIRED"):
        await escrows.fail_hold(session, contract, escrow, escrows.HOLD_DECLINED)
    elif authorization.status == "PENDING":
        # PayPal is reviewing the payment; the webhook or reconciliation finishes the hold.
        escrow.paypal_authorization_id = authorization.id
        note(
            session,
            contract,
            "PayPal is reviewing the hold. We'll continue as soon as it confirms.",
            actor=escrows.PAYPAL,
        )
    else:
        await escrows.record_hold(session, ctx.settings, contract, escrow, authorization)


async def _authorized_order(
    session: AsyncSession, ctx: JobContext, contract: Contract, escrow: Escrow
) -> Order | None:
    """Create (or, after payer approval, authorize) the order. None while the payer acts."""
    if escrow.status == "payer_action" and escrow.paypal_order_id:
        return await ctx.paypal.authorize_order(
            escrow.paypal_order_id, operation=_operation(contract, escrow, "authorize")
        )

    vault_id = None
    if ctx.settings.paypal_funding_mode == "vault":
        account = await FundingService(session, ctx.settings, ctx.paypal).connected_account(
            contract.hirer_org_id
        )
        if account is None or not account.vault_token_id:
            await escrows.fail_hold(session, contract, escrow, escrows.HOLD_DECLINED)
            return None
        vault_id = account.vault_token_id

    return_url = f"{ctx.paypal.config.return_base_url}{escrows.ORDER_RETURN_PATH}"
    order = await ctx.paypal.create_authorize_order(
        operation=_operation(contract, escrow, "create_order"),
        amount=contract.amount,
        reference_id=contract.id,
        custom_id=contract.id,
        invoice_id=f"C-{contract.number}",
        description=contract.title,
        vault_id=vault_id,
        return_url=None if vault_id else return_url,
        cancel_url=None if vault_id else f"{return_url}?outcome=cancel",
    )
    escrow.paypal_order_id = order.id
    if order.authorization is not None:
        return order
    if order.status == "PAYER_ACTION_REQUIRED":
        escrow.status = "payer_action"
        escrow.payer_action_url = order.payer_action_url
        return None
    return await ctx.paypal.authorize_order(
        order.id, operation=_operation(contract, escrow, "authorize")
    )


async def give_up(session: AsyncSession, ctx: JobContext, payload: Payload, error: str) -> None:
    contract = await lock_contract(session, payload["contract_id"])
    if contract.state == State.FUNDING:
        await escrows.mark_inconsistent(
            session,
            contract,
            "We couldn't confirm the hold with PayPal. An admin will check it.",
            data={"error": error},
        )


HANDLER = JobHandler(run=run, on_give_up=give_up)
