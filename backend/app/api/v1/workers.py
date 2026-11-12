from decimal import Decimal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    OrgPrincipal,
    get_app_settings,
    get_session,
    require_hirer,
    require_org,
    require_provider,
)
from app.core.config import Settings
from app.core.errors import AppError, NotFoundError
from app.domain.policy import WORK_TYPES
from app.models import Organization, Worker
from app.schemas.common import Page, PageParams
from app.schemas.workers import (
    RegisterAgentRequest,
    RegisterHumanRequest,
    VerificationOut,
    VerificationStepOut,
    WorkerOut,
    worker_out,
)
from app.services import worker_registry

router = APIRouter(prefix="/workers", tags=["workers"])


def _page(
    page: int = Query(default=1, ge=1), page_size: int = Query(default=24, ge=1, le=100)
) -> PageParams:
    return PageParams(page=page, page_size=page_size)


async def _named(session: AsyncSession, worker: Worker) -> WorkerOut:
    org_name = await session.scalar(
        select(Organization.name).where(Organization.id == worker.org_id)
    )
    return worker_out(worker, org_name or "")


@router.get("", dependencies=[Depends(require_hirer)])
async def marketplace(
    category: str | None = None,
    kind: str | None = Query(default=None, pattern="^(agent|human)$"),
    min_price: Decimal | None = Query(default=None, ge=0),
    max_price: Decimal | None = Query(default=None, ge=0),
    min_reputation: int | None = Query(default=None, ge=0, le=100),
    verified_only: bool = True,
    params: PageParams = Depends(_page),
    principal: OrgPrincipal = Depends(require_org),
    session: AsyncSession = Depends(get_session),
) -> Page[WorkerOut]:
    """Verified workers other organizations offer. Suspended workers are never listed."""
    statuses = ["verified"] if verified_only else ["verified", "unhealthy"]
    conditions = [Worker.status.in_(statuses), Worker.org_id != principal.org_id]
    if category:
        if category not in WORK_TYPES:
            raise AppError(f"Unknown category {category!r}.", status=422, code="UNKNOWN_CATEGORY")
        conditions.append(func.json_contains(Worker.categories, f'"{category}"'))
    if kind:
        conditions.append(Worker.kind == kind)
    if min_price is not None:
        conditions.append(Worker.price >= min_price)
    if max_price is not None:
        conditions.append(Worker.price <= max_price)
    if min_reputation is not None:
        conditions.append(Worker.reputation >= min_reputation)
    total = await session.scalar(select(func.count()).select_from(Worker).where(*conditions)) or 0
    rows = await session.execute(
        select(Worker, Organization.name)
        .join(Organization, Organization.id == Worker.org_id)
        .where(*conditions)
        .order_by(Worker.reputation.desc(), Worker.display_name)
        .offset(params.offset)
        .limit(params.page_size)
    )
    return Page(
        items=[worker_out(worker, org_name) for worker, org_name in rows],
        page=params.page,
        page_size=params.page_size,
        total=total,
    )


@router.get("/mine", dependencies=[Depends(require_provider)])
async def my_workers(
    principal: OrgPrincipal = Depends(require_org),
    session: AsyncSession = Depends(get_session),
) -> list[WorkerOut]:
    org_name = await session.scalar(
        select(Organization.name).where(Organization.id == principal.org_id)
    )
    workers = await session.scalars(
        select(Worker).where(Worker.org_id == principal.org_id).order_by(Worker.created_at)
    )
    return [worker_out(worker, org_name or "") for worker in workers]


@router.post(
    "/agent", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(require_provider)]
)
async def register_agent(
    data: RegisterAgentRequest,
    principal: OrgPrincipal = Depends(require_org),
    settings: Settings = Depends(get_app_settings),
    session: AsyncSession = Depends(get_session),
) -> WorkerOut:
    worker = await worker_registry.register_agent(
        session,
        settings,
        org_id=principal.org_id,
        base_url=data.base_url,
        price=data.price,
        currency="USD",
        categories=list(data.categories),
        auth_token=data.auth_token,
    )
    await session.commit()
    return await _named(session, worker)


@router.post(
    "/human", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_provider)]
)
async def register_human(
    data: RegisterHumanRequest,
    principal: OrgPrincipal = Depends(require_org),
    session: AsyncSession = Depends(get_session),
) -> WorkerOut:
    worker = await worker_registry.register_human(
        session,
        org_id=principal.org_id,
        display_name=data.display_name,
        description=data.description,
        price=data.price,
        currency="USD",
        categories=list(data.categories),
    )
    await session.commit()
    return await _named(session, worker)


@router.get("/{worker_id}")
async def get_worker(
    worker_id: str,
    principal: OrgPrincipal = Depends(require_org),
    session: AsyncSession = Depends(get_session),
) -> WorkerOut:
    worker = await session.get(Worker, worker_id)
    if worker is None or (worker.org_id != principal.org_id and worker.status != "verified"):
        raise NotFoundError("This worker doesn't exist.", code="WORKER_NOT_FOUND")
    return await _named(session, worker)


@router.get("/{worker_id}/verification", dependencies=[Depends(require_provider)])
async def verification(
    worker_id: str,
    principal: OrgPrincipal = Depends(require_org),
    session: AsyncSession = Depends(get_session),
) -> VerificationOut:
    worker = await session.get(Worker, worker_id)
    if worker is None or worker.org_id != principal.org_id:
        raise NotFoundError("This worker doesn't exist.", code="WORKER_NOT_FOUND")
    steps = await worker_registry.verification_steps(session, worker.id)
    return VerificationOut(
        status=worker.status,
        steps=[VerificationStepOut.model_validate(step) for step in steps],
    )


@router.post(
    "/{worker_id}/verify",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_provider)],
)
async def verify_again(
    worker_id: str,
    principal: OrgPrincipal = Depends(require_org),
    session: AsyncSession = Depends(get_session),
) -> WorkerOut:
    worker = await worker_registry.retry_verification(
        session, org_id=principal.org_id, worker_id=worker_id
    )
    await session.commit()
    return await _named(session, worker)
