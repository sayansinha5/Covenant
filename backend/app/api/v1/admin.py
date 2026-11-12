from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Principal, get_session, require_platform_admin
from app.core.errors import ConflictError, NotFoundError
from app.core.logging import get_logger
from app.models import Contract, Organization, WebhookEvent, Worker
from app.schemas.admin import (
    AdminWorkerOut,
    ModerationRequest,
    ReconciliationRunOut,
    WebhookEventOut,
)
from app.schemas.common import Page, PageParams
from app.services import reconcile

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_platform_admin)])
logger = get_logger("covenant.admin")


def _page_params(
    page: int = Query(default=1, ge=1), page_size: int = Query(default=25, ge=1, le=100)
) -> PageParams:
    return PageParams(page=page, page_size=page_size)


def _worker_out(worker: Worker, org_name: str) -> AdminWorkerOut:
    return AdminWorkerOut(
        id=worker.id,
        display_name=worker.display_name,
        kind=worker.kind,
        org_id=worker.org_id,
        org_name=org_name,
        base_url=worker.base_url,
        categories=worker.categories,
        price=worker.price,
        currency=worker.currency,
        status=worker.status,
        reputation=worker.reputation,
        suspended_reason=worker.suspended_reason,
        created_at=worker.created_at,
    )


@router.get("/workers")
async def list_workers(
    params: PageParams = Depends(_page_params),
    session: AsyncSession = Depends(get_session),
) -> Page[AdminWorkerOut]:
    total = await session.scalar(select(func.count()).select_from(Worker)) or 0
    rows = await session.execute(
        select(Worker, Organization.name)
        .join(Organization, Organization.id == Worker.org_id)
        .order_by(Worker.created_at.desc())
        .offset(params.offset)
        .limit(params.page_size)
    )
    return Page(
        items=[_worker_out(worker, org_name) for worker, org_name in rows],
        page=params.page,
        page_size=params.page_size,
        total=total,
    )


async def _locked_worker(session: AsyncSession, worker_id: str) -> tuple[Worker, str]:
    row = (
        await session.execute(
            select(Worker, Organization.name)
            .join(Organization, Organization.id == Worker.org_id)
            .where(Worker.id == worker_id)
            .with_for_update(of=Worker)
        )
    ).first()
    if row is None:
        raise NotFoundError("This worker doesn't exist.", code="WORKER_NOT_FOUND")
    return row[0], row[1]


@router.post("/workers/{worker_id}/suspend")
async def suspend_worker(
    worker_id: str,
    data: ModerationRequest,
    admin: Principal = Depends(require_platform_admin),
    session: AsyncSession = Depends(get_session),
) -> AdminWorkerOut:
    worker, org_name = await _locked_worker(session, worker_id)
    if worker.status == "suspended":
        raise ConflictError("This worker is already suspended.", code="WORKER_SUSPENDED")
    worker.status = "suspended"
    worker.suspended_reason = data.reason
    await session.commit()
    logger.info("worker_suspended", worker_id=worker.id, admin_id=admin.user_id, reason=data.reason)
    return _worker_out(worker, org_name)


@router.post("/workers/{worker_id}/reinstate")
async def reinstate_worker(
    worker_id: str,
    data: ModerationRequest,
    admin: Principal = Depends(require_platform_admin),
    session: AsyncSession = Depends(get_session),
) -> AdminWorkerOut:
    worker, org_name = await _locked_worker(session, worker_id)
    if worker.status != "suspended":
        raise ConflictError(
            "Only suspended workers can be reinstated.", code="WORKER_NOT_SUSPENDED"
        )
    # A reinstated worker is listed again only if it had passed verification.
    worker.status = "verified" if worker.verified_at else "pending"
    worker.suspended_reason = None
    await session.commit()
    logger.info(
        "worker_reinstated", worker_id=worker.id, admin_id=admin.user_id, reason=data.reason
    )
    return _worker_out(worker, org_name)


@router.get("/webhook-events")
async def list_webhook_events(
    params: PageParams = Depends(_page_params),
    session: AsyncSession = Depends(get_session),
) -> Page[WebhookEventOut]:
    total = await session.scalar(select(func.count()).select_from(WebhookEvent)) or 0
    rows = await session.execute(
        select(WebhookEvent, Contract.number)
        .outerjoin(Contract, Contract.id == WebhookEvent.contract_id)
        .order_by(WebhookEvent.received_at.desc())
        .offset(params.offset)
        .limit(params.page_size)
    )
    items = [
        WebhookEventOut(
            id=event.id,
            paypal_event_id=event.paypal_event_id,
            claimed_event_id=None if event.verified else event.payload.get("claimed_event_id"),
            event_type=event.event_type,
            resource_id=event.resource_id,
            verified=event.verified,
            processed=event.processed,
            result=event.result,
            outcome=event.outcome,
            error=event.error,
            contract_id=event.contract_id,
            contract_number=f"C-{number}" if number else None,
            received_at=event.received_at,
            processed_at=event.processed_at,
        )
        for event, number in rows
    ]
    return Page(items=items, page=params.page, page_size=params.page_size, total=total)


@router.post("/reconcile", status_code=status.HTTP_202_ACCEPTED)
async def run_reconciliation(
    admin: Principal = Depends(require_platform_admin),
    session: AsyncSession = Depends(get_session),
) -> ReconciliationRunOut:
    """Queue a reconciliation run (or return the one in progress); poll `/reconcile/last`."""
    run = await reconcile.request(session, requested_by=admin.user_id)
    await session.commit()
    return ReconciliationRunOut.model_validate(run)


@router.get("/reconcile/last")
async def last_reconciliation(
    session: AsyncSession = Depends(get_session),
) -> ReconciliationRunOut | None:
    run = await reconcile.last_run(session)
    return ReconciliationRunOut.model_validate(run) if run else None
