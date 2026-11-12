"""Search, the settlement calendar, Channel3 catalog search and the Astropods fleet."""

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    OrgPrincipal,
    get_app_settings,
    get_session,
    require_hirer,
    require_org,
)
from app.core.config import Settings
from app.core.errors import AppError, NotFoundError
from app.core.rate_limit import RateLimiter
from app.integrations.channel3 import CatalogError, search_catalog
from app.models import Organization
from app.schemas.operate import CatalogOut, CatalogQuery, FleetOut, ScheduleOut, SearchOut
from app.services.fleet import fleet_view
from app.services.schedule import settlement_schedule
from app.services.search import search_work

router = APIRouter(tags=["operate"])


@router.get("/search", response_model=SearchOut)
async def get_search(
    q: str = Query(min_length=1, max_length=120),
    principal: OrgPrincipal = Depends(require_org),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_app_settings),
) -> dict[str, object]:
    org = await session.get(Organization, principal.org_id)
    if org is None:
        raise NotFoundError("This organization no longer exists.")
    return await search_work(session, settings, org, q)


@router.get("/schedule", response_model=ScheduleOut)
async def get_schedule(
    principal: OrgPrincipal = Depends(require_org),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_app_settings),
) -> dict[str, object]:
    return await settlement_schedule(session, settings, principal.org_id)


@router.post("/catalog/search", response_model=CatalogOut)
async def post_catalog_search(
    body: CatalogQuery,
    request: Request,
    principal: OrgPrincipal = Depends(require_org),
    _hirer: Organization = Depends(require_hirer),
    settings: Settings = Depends(get_app_settings),
) -> CatalogOut:
    limiter: RateLimiter = request.app.state.rate_limiter
    limiter.hit(settings.rate_limit_assistant, "catalog", principal.org_id)
    try:
        products = await search_catalog(settings, body.query.strip(), org_id=principal.org_id)
    except CatalogError as exc:
        raise AppError(exc.detail, status=exc.status, code=exc.code) from exc
    return CatalogOut(query=body.query.strip(), products=products)


@router.get("/fleet", response_model=FleetOut)
async def get_fleet(
    principal: OrgPrincipal = Depends(require_org),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_app_settings),
) -> dict[str, object]:
    return await fleet_view(session, settings, principal.org_id)
