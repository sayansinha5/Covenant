from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    OrgPrincipal,
    get_app_settings,
    get_session,
    require_hirer,
    require_org,
    require_owner,
)
from app.core.config import Settings
from app.core.errors import ForbiddenError
from app.core.rate_limit import auth_rate_limit
from app.core.security import verify_password
from app.models import User
from app.schemas.mandate import MandateCreate, MandateOut, MandateOverview, work_type_options
from app.services import mandates

router = APIRouter(prefix="/mandate", tags=["mandate"], dependencies=[Depends(require_hirer)])


@router.get("")
async def get_mandate(
    principal: OrgPrincipal = Depends(require_org),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_app_settings),
) -> MandateOverview:
    active = await mandates.active_mandate(session, principal.org_id)
    described = await mandates.describe(session, [active]) if active else []
    return MandateOverview(
        active=described[0] if described else None,
        defaults=mandates.mandate_defaults(settings),
        work_types=work_type_options(),
    )


@router.get("/versions")
async def mandate_versions(
    principal: OrgPrincipal = Depends(require_org),
    session: AsyncSession = Depends(get_session),
) -> list[MandateOut]:
    return await mandates.describe(session, await mandates.list_versions(session, principal.org_id))


@router.post("", status_code=status.HTTP_201_CREATED, dependencies=[Depends(auth_rate_limit)])
async def sign_mandate(
    data: MandateCreate,
    principal: OrgPrincipal = Depends(require_owner),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_app_settings),
) -> MandateOut:
    user = await session.get(User, principal.user_id)
    if user is None or not verify_password(user.password_hash, data.password):
        raise ForbiddenError("Password is incorrect.", code="PASSWORD_INCORRECT")
    mandate = await mandates.sign_mandate(
        session,
        org_id=principal.org_id,
        user_id=principal.user_id,
        data=data,
        currency=settings.currency,
    )
    await session.commit()
    return (await mandates.describe(session, [mandate]))[0]
