from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    OrgPrincipal,
    get_app_settings,
    get_paypal,
    get_session,
    money_rate_limit,
    require_hirer,
    require_manager,
)
from app.api.idempotency import IdempotentRequest, idempotent_request, remember, replay_or_reserve
from app.core.config import Settings
from app.integrations.paypal import PayPalClient
from app.models import User
from app.schemas.contracts import AgreeOut, CancelOut, ContractSummary, PolicyOut
from app.services import escrow
from app.services.contracts import Actor

router = APIRouter(
    prefix="/contracts",
    tags=["contracts"],
    dependencies=[Depends(require_hirer), Depends(money_rate_limit)],
)


async def _actor(session: AsyncSession, principal: OrgPrincipal) -> tuple[Actor, str]:
    user = await session.get_one(User, principal.user_id)
    return Actor(principal.actor_type, principal.user_id), user.full_name


@router.post("/{contract_id}/agree", status_code=status.HTTP_202_ACCEPTED, response_model=AgreeOut)
async def agree(
    contract_id: str,
    idempotency: IdempotentRequest = Depends(idempotent_request),
    principal: OrgPrincipal = Depends(require_manager),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_app_settings),
    paypal: PayPalClient = Depends(get_paypal),
) -> JSONResponse:
    """Agree to a contract: the mandate is checked and the amount is held in PayPal in the
    background (the contract moves to `funding`, then `funded`)."""
    replay = await replay_or_reserve(session, idempotency)
    if replay is not None:
        return replay
    actor, name = await _actor(session, principal)
    contract, decision = await escrow.agree(
        session,
        settings,
        paypal,
        org_id=principal.org_id,
        contract_id=contract_id,
        actor=actor,
        actor_name=name,
    )
    body = AgreeOut(
        contract=ContractSummary.of(contract),
        policy=PolicyOut(
            outcome=decision.outcome,
            code=decision.code,
            reason=decision.reason,
            mandate_version=decision.mandate_version,
        ),
    ).model_dump(mode="json")
    response = await remember(session, idempotency, status.HTTP_202_ACCEPTED, body)
    await session.commit()
    return response


@router.post("/{contract_id}/cancel", response_model=CancelOut)
async def cancel(
    contract_id: str,
    idempotency: IdempotentRequest = Depends(idempotent_request),
    principal: OrgPrincipal = Depends(require_manager),
    session: AsyncSession = Depends(get_session),
) -> JSONResponse:
    """Decline or cancel before the worker accepts; a hold is released in the background."""
    replay = await replay_or_reserve(session, idempotency)
    if replay is not None:
        return replay
    actor, name = await _actor(session, principal)
    contract = await escrow.cancel(
        session, org_id=principal.org_id, contract_id=contract_id, actor=actor, actor_name=name
    )
    body = CancelOut(contract=ContractSummary.of(contract)).model_dump(mode="json")
    response = await remember(session, idempotency, status.HTTP_200_OK, body)
    await session.commit()
    return response
