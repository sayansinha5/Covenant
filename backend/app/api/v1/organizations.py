from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    OrgPrincipal,
    Principal,
    get_app_settings,
    get_paypal,
    get_principal,
    get_session,
    get_token_issuer,
    require_manager,
    require_org,
)
from app.core.config import Settings
from app.core.errors import ConflictError
from app.core.security import TokenIssuer
from app.db.base import utcnow
from app.integrations.paypal import PayPalClient
from app.schemas.common import ResponseModel
from app.schemas.identity import OrganizationCreate, OrganizationOut, OrganizationUpdate
from app.services import mandates, organizations
from app.services.funding import FundingService
from app.services.identity import IdentityService

router = APIRouter(prefix="/orgs", tags=["organizations"])


class OrganizationCreated(ResponseModel):
    organization: OrganizationOut
    # The caller's token now needs the new org and owner role in its claims.
    access_token: str
    expires_in: int


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_organization(
    data: OrganizationCreate,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_app_settings),
    issuer: TokenIssuer = Depends(get_token_issuer),
) -> OrganizationCreated:
    org = await organizations.create_organization(session, principal.user_id, data)
    access, expires_in = await IdentityService(session, settings, issuer).reissue_access(
        principal.user_id
    )
    await session.commit()
    return OrganizationCreated(
        organization=OrganizationOut.model_validate(org),
        access_token=access,
        expires_in=expires_in,
    )


@router.get("/current")
async def current_organization(
    principal: OrgPrincipal = Depends(require_org),
    session: AsyncSession = Depends(get_session),
) -> OrganizationOut:
    return OrganizationOut.model_validate(
        await organizations.get_organization(session, principal.org_id)
    )


@router.patch("/current")
async def update_current_organization(
    data: OrganizationUpdate,
    principal: OrgPrincipal = Depends(require_manager),
    session: AsyncSession = Depends(get_session),
) -> OrganizationOut:
    org = await organizations.update_organization(session, principal.org_id, data)
    await session.commit()
    return OrganizationOut.model_validate(org)


@router.post("/current/onboarding/complete")
async def complete_onboarding(
    principal: OrgPrincipal = Depends(require_manager),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_app_settings),
    paypal: PayPalClient = Depends(get_paypal),
) -> OrganizationOut:
    org = await organizations.get_organization(session, principal.org_id)
    missing = []
    if org.can_hire:
        if not await FundingService(session, settings, paypal).is_connected(org.id):
            missing.append("connect PayPal")
        if await mandates.active_mandate(session, org.id) is None:
            missing.append("sign a mandate")
    if org.can_provide and not org.payout_email:
        missing.append("add a PayPal email for payouts")
    if missing:
        raise ConflictError(
            f"To finish setup, {' and '.join(missing)}.", code="ONBOARDING_INCOMPLETE"
        )
    if org.onboarded_at is None:
        org.onboarded_at = utcnow()
        await session.commit()
    return OrganizationOut.model_validate(org)
