"""Contracts, approvals, jobs, ledger, overview, notifications, earnings and API keys."""

from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    OrgPrincipal,
    get_app_settings,
    get_paypal,
    get_session,
    require_hirer,
    require_manager,
    require_org,
    require_provider,
)
from app.core.config import Settings
from app.integrations.paypal import PayPalClient
from app.models import Organization, User
from app.schemas.common import Page, PageParams
from app.schemas.contracts import ContractSummary
from app.schemas.workspace import (
    ApiKeyCreated,
    ApiKeyIn,
    ApiKeyOut,
    AppealDecisionIn,
    AppealIn,
    AppealOut,
    ApprovalOut,
    BandIn,
    ChangeIn,
    ContractDetail,
    ContractListItem,
    DeliveryIn,
    DraftIn,
    EarningsOut,
    EscrowOut,
    LedgerRow,
    NotificationOut,
    OverviewOut,
    PayoutOut,
    TimelineEvent,
    VerdictOut,
)
from app.services import api_keys, execution, hiring, records
from app.services.contracts import Actor

router = APIRouter(tags=["workspace"])


def _page(
    page: int = Query(default=1, ge=1), page_size: int = Query(default=25, ge=1, le=100)
) -> PageParams:
    return PageParams(page=page, page_size=page_size)


async def _named(session: AsyncSession, principal: OrgPrincipal) -> tuple[Actor, str]:
    user = await session.get_one(User, principal.user_id)
    return Actor(principal.actor_type, principal.user_id), user.full_name


@router.get("/overview", response_model=OverviewOut)
async def get_overview(
    principal: OrgPrincipal = Depends(require_org),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    return await records.overview(session, principal.org_id)


@router.get("/contracts", response_model=Page[ContractListItem])
async def get_contracts(
    role: str | None = Query(default=None, pattern="^(hirer|provider)$"),
    page: PageParams = Depends(_page),
    principal: OrgPrincipal = Depends(require_org),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    items, total = await records.list_contracts(
        session, principal.org_id, role=role, offset=page.offset, limit=page.page_size
    )
    return {"items": items, "page": page.page, "page_size": page.page_size, "total": total}


@router.get("/contracts/{contract_id}", response_model=ContractDetail)
async def get_contract(
    contract_id: str,
    principal: OrgPrincipal = Depends(require_org),
    session: AsyncSession = Depends(get_session),
) -> ContractDetail:
    return _detail(await records.contract_detail(session, principal.org_id, contract_id))


@router.post("/contracts", response_model=ContractDetail, status_code=201)
async def post_contract(
    body: DraftIn,
    principal: OrgPrincipal = Depends(require_manager),
    _hirer: Organization = Depends(require_hirer),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_app_settings),
    paypal: PayPalClient = Depends(get_paypal),
) -> ContractDetail:
    who, _name = await _named(session, principal)
    contract, _card = await hiring.draft_contract(
        session,
        settings,
        paypal,
        org_id=principal.org_id,
        user_actor=who,
        worker_id=body.worker_id,
        request_text=body.request_text,
        budget=body.budget,
    )
    await session.commit()
    return _detail(await records.contract_detail(session, principal.org_id, contract.id))


@router.post("/contracts/{contract_id}/revise", response_model=ContractSummary)
async def post_revise(
    contract_id: str,
    body: ChangeIn,
    principal: OrgPrincipal = Depends(require_manager),
    _hirer: Organization = Depends(require_hirer),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_app_settings),
) -> ContractSummary:
    who, _name = await _named(session, principal)
    contract = await hiring.revise_contract(
        session,
        settings,
        org_id=principal.org_id,
        contract_id=contract_id,
        change_request=body.change_request,
        user_actor=who,
    )
    await session.commit()
    return ContractSummary.of(contract)


@router.post("/contracts/{contract_id}/accept", response_model=ContractSummary)
async def post_accept(
    contract_id: str,
    principal: OrgPrincipal = Depends(require_org),
    _provider: Organization = Depends(require_provider),
    session: AsyncSession = Depends(get_session),
) -> ContractSummary:
    who, name = await _named(session, principal)
    contract = await execution.accept_offer(
        session, org_id=principal.org_id, contract_id=contract_id, actor=who, actor_name=name
    )
    await session.commit()
    return ContractSummary.of(contract)


@router.post("/contracts/{contract_id}/decline", response_model=ContractSummary)
async def post_decline(
    contract_id: str,
    principal: OrgPrincipal = Depends(require_org),
    _provider: Organization = Depends(require_provider),
    session: AsyncSession = Depends(get_session),
) -> ContractSummary:
    who, name = await _named(session, principal)
    contract = await execution.decline_offer(
        session, org_id=principal.org_id, contract_id=contract_id, actor=who, actor_name=name
    )
    await session.commit()
    return ContractSummary.of(contract)


@router.post("/contracts/{contract_id}/deliver", response_model=ContractSummary)
async def post_deliver(
    contract_id: str,
    body: DeliveryIn,
    principal: OrgPrincipal = Depends(require_org),
    _provider: Organization = Depends(require_provider),
    session: AsyncSession = Depends(get_session),
) -> ContractSummary:
    who, name = await _named(session, principal)
    content: Any = body.content
    if body.notes:
        content = {"delivery": body.content, "notes": body.notes}
    contract = await execution.submit_delivery(
        session,
        org_id=principal.org_id,
        contract_id=contract_id,
        actor=who,
        actor_name=name,
        content=content,
        file_ids=body.file_ids,
    )
    await session.commit()
    return ContractSummary.of(contract)


@router.post("/contracts/{contract_id}/appeal", response_model=AppealOut, status_code=201)
async def post_appeal(
    contract_id: str,
    body: AppealIn,
    principal: OrgPrincipal = Depends(require_org),
    _provider: Organization = Depends(require_provider),
    session: AsyncSession = Depends(get_session),
) -> AppealOut:
    who, _name = await _named(session, principal)
    appeal = await execution.open_appeal(
        session,
        org_id=principal.org_id,
        contract_id=contract_id,
        actor=who,
        argument=body.argument,
    )
    await session.commit()
    return AppealOut.model_validate(appeal)


@router.post("/contracts/{contract_id}/accept-verdict", response_model=ContractSummary)
async def post_accept_verdict(
    contract_id: str,
    principal: OrgPrincipal = Depends(require_org),
    _provider: Organization = Depends(require_provider),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_app_settings),
) -> ContractSummary:
    who, name = await _named(session, principal)
    contract = await execution.accept_verdict(
        session,
        settings,
        org_id=principal.org_id,
        contract_id=contract_id,
        actor=who,
        actor_name=name,
    )
    await session.commit()
    return ContractSummary.of(contract)


@router.post("/contracts/{contract_id}/band", response_model=ContractSummary)
async def post_band(
    contract_id: str,
    body: BandIn,
    principal: OrgPrincipal = Depends(require_manager),
    _hirer: Organization = Depends(require_hirer),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_app_settings),
) -> ContractSummary:
    who, name = await _named(session, principal)
    contract = await execution.choose_band(
        session,
        settings,
        org_id=principal.org_id,
        contract_id=contract_id,
        band=body.band,
        actor=who,
        actor_name=name,
    )
    await session.commit()
    return ContractSummary.of(contract)


@router.post("/contracts/{contract_id}/appeal-decision", response_model=ContractSummary)
async def post_appeal_decision(
    contract_id: str,
    body: AppealDecisionIn,
    principal: OrgPrincipal = Depends(require_manager),
    _hirer: Organization = Depends(require_hirer),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_app_settings),
) -> ContractSummary:
    who, name = await _named(session, principal)
    contract = await execution.decide_appeal(
        session,
        settings,
        org_id=principal.org_id,
        contract_id=contract_id,
        accept=body.accept,
        actor=who,
        actor_name=name,
        note_text=body.note,
    )
    await session.commit()
    return ContractSummary.of(contract)


@router.get("/approvals", response_model=list[ApprovalOut])
async def get_approvals(
    principal: OrgPrincipal = Depends(require_org),
    _hirer: Organization = Depends(require_hirer),
    session: AsyncSession = Depends(get_session),
) -> list[ApprovalOut]:
    rows = await records.list_approvals(session, principal.org_id)
    return [ApprovalOut.model_validate(row) for row in rows]


@router.post("/approvals/{approval_id}/approve", response_model=ContractSummary)
async def post_approve(
    approval_id: str,
    principal: OrgPrincipal = Depends(require_manager),
    _hirer: Organization = Depends(require_hirer),
    session: AsyncSession = Depends(get_session),
) -> ContractSummary:
    who, name = await _named(session, principal)
    contract = await hiring.decide_approval(
        session,
        org_id=principal.org_id,
        approval_id=approval_id,
        actor=who,
        actor_name=name,
        approve=True,
    )
    await session.commit()
    return ContractSummary.of(contract)


@router.post("/approvals/{approval_id}/reject", response_model=ContractSummary)
async def post_reject(
    approval_id: str,
    principal: OrgPrincipal = Depends(require_manager),
    _hirer: Organization = Depends(require_hirer),
    session: AsyncSession = Depends(get_session),
) -> ContractSummary:
    who, name = await _named(session, principal)
    contract = await hiring.decide_approval(
        session,
        org_id=principal.org_id,
        approval_id=approval_id,
        actor=who,
        actor_name=name,
        approve=False,
    )
    await session.commit()
    return ContractSummary.of(contract)


@router.get("/ledger", response_model=Page[LedgerRow])
async def get_ledger(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=500),
    principal: OrgPrincipal = Depends(require_org),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    params = PageParams(page=page, page_size=page_size)
    rows, total = await records.ledger_page(
        session, principal.org_id, offset=params.offset, limit=params.page_size
    )
    return {
        "items": [LedgerRow.model_validate(row) for row in rows],
        "page": params.page,
        "page_size": params.page_size,
        "total": total,
    }


@router.get("/ledger/export.csv")
async def export_ledger(
    principal: OrgPrincipal = Depends(require_org),
    session: AsyncSession = Depends(get_session),
) -> Response:
    body = await records.ledger_csv(session, principal.org_id)
    return Response(
        body,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="covenant-ledger.csv"'},
    )


@router.get("/notifications", response_model=list[NotificationOut])
async def get_notifications(
    principal: OrgPrincipal = Depends(require_org),
    session: AsyncSession = Depends(get_session),
) -> list[NotificationOut]:
    rows = await records.notifications(session, principal.org_id)
    return [NotificationOut.model_validate(row) for row in rows]


@router.post("/notifications/read-all", status_code=204)
async def post_read_all(
    principal: OrgPrincipal = Depends(require_org),
    session: AsyncSession = Depends(get_session),
) -> Response:
    await records.mark_read(session, principal.org_id, None)
    await session.commit()
    return Response(status_code=204)


@router.post("/notifications/{notification_id}/read", status_code=204)
async def post_read(
    notification_id: str,
    principal: OrgPrincipal = Depends(require_org),
    session: AsyncSession = Depends(get_session),
) -> Response:
    await records.mark_read(session, principal.org_id, notification_id)
    await session.commit()
    return Response(status_code=204)


@router.get("/earnings/summary", response_model=EarningsOut)
async def get_earnings(
    principal: OrgPrincipal = Depends(require_org),
    _provider: Organization = Depends(require_provider),
    session: AsyncSession = Depends(get_session),
) -> EarningsOut:
    payload = await records.earnings(session, principal.org_id)
    return EarningsOut(
        paid=payload["paid"],
        pending=payload["pending"],
        payouts=[PayoutOut.model_validate(row) for row in payload["payouts"]],
    )


@router.get("/api-keys", response_model=list[ApiKeyOut])
async def get_keys(
    principal: OrgPrincipal = Depends(require_org),
    session: AsyncSession = Depends(get_session),
) -> list[ApiKeyOut]:
    return [
        ApiKeyOut.model_validate(row) for row in await api_keys.list_keys(session, principal.org_id)
    ]


@router.post("/api-keys", response_model=ApiKeyCreated, status_code=201)
async def post_key(
    body: ApiKeyIn,
    principal: OrgPrincipal = Depends(require_manager),
    session: AsyncSession = Depends(get_session),
) -> ApiKeyCreated:
    row, secret = await api_keys.create_key(
        session, org_id=principal.org_id, user_id=principal.user_id, name=body.name
    )
    created = ApiKeyCreated(
        id=row.id,
        name=row.name,
        prefix=row.prefix,
        created_at=row.created_at,
        last_used_at=row.last_used_at,
        revoked_at=row.revoked_at,
        key=secret,
    )
    await session.commit()
    return created


@router.delete("/api-keys/{key_id}", status_code=204)
async def delete_key(
    key_id: str,
    principal: OrgPrincipal = Depends(require_manager),
    session: AsyncSession = Depends(get_session),
) -> Response:
    await api_keys.revoke_key(session, org_id=principal.org_id, key_id=key_id)
    await session.commit()
    return Response(status_code=204)


def _detail(payload: dict[str, Any]) -> ContractDetail:
    contract = payload["contract"]
    verdict = payload["verdict"]
    escrow = payload["escrow"]
    appeal = payload["appeal"]
    delivery = payload["delivery"]
    return ContractDetail(
        id=contract.id,
        number=f"C-{contract.number}",
        title=contract.title,
        state=contract.state,
        amount=contract.amount,
        currency=contract.currency,
        worker_name=payload["worker_name"],
        role=payload["role"],
        updated_at=contract.updated_at,
        work_type=contract.work_type,
        request_text=contract.request_text,
        spec=contract.spec,
        spec_fingerprint=payload["spec_fingerprint"],
        deadline_at=contract.deadline_at,
        appeal_window_ends_at=contract.appeal_window_ends_at,
        worker_kind=payload["worker_kind"],
        hirer_name=payload["hirer_name"],
        provider_name=payload["provider_name"],
        events=[
            TimelineEvent(
                id=event.id,
                event=event.event,
                message=event.message,
                created_at=event.created_at,
                actor_type=event.actor_type,
            )
            for event in payload["events"]
        ],
        delivery=None if delivery is None else delivery.content,
        verdict=None
        if verdict is None
        else VerdictOut(
            result=verdict.result,
            pass_ratio=str(verdict.pass_ratio),
            overall_score=str(verdict.overall_score),
            reasoning=verdict.reasoning,
            item_results=list(verdict.item_results or []),
            manipulation=verdict.manipulation,
        ),
        escrow=None
        if escrow is None
        else EscrowOut(
            status=escrow.status,
            amount_held=escrow.amount_held,
            amount_captured=escrow.amount_captured,
            amount_released=escrow.amount_released,
            settlement=escrow.settlement,
        ),
        appeal=None if appeal is None else AppealOut.model_validate(appeal),
    )
