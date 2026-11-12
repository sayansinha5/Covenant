from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ConflictError, NotFoundError
from app.core.ids import uuid7
from app.models import Membership, Organization
from app.schemas.identity import OrganizationCreate, OrganizationUpdate


async def create_organization(
    session: AsyncSession, user_id: str, data: OrganizationCreate
) -> Organization:
    # One organization per user in the PoC (member invitations are out of scope).
    existing = await session.scalar(
        select(Membership.id).where(Membership.user_id == user_id).with_for_update()
    )
    if existing is not None:
        raise ConflictError("You already belong to an organization.", code="ORGANIZATION_EXISTS")
    org = Organization(
        id=uuid7(),
        name=data.name,
        industry=data.industry,
        country=data.country,
        can_hire=data.can_hire,
        can_provide=data.can_provide,
        assistant_name=data.assistant_name if data.can_hire else None,
    )
    session.add(org)
    await session.flush()
    session.add(Membership(id=uuid7(), user_id=user_id, org_id=org.id, role="owner"))
    await session.flush()
    return org


async def get_organization(session: AsyncSession, org_id: str) -> Organization:
    org = await session.get(Organization, org_id)
    if org is None:
        raise NotFoundError("Organization not found.")
    return org


async def update_organization(
    session: AsyncSession, org_id: str, data: OrganizationUpdate
) -> Organization:
    org = await get_organization(session, org_id)
    changes = data.model_dump(exclude_unset=True)
    for field, value in changes.items():
        if field in {"name", "industry", "country", "can_hire", "can_provide"} and value is None:
            raise AppError(f"{field} can't be empty.", code="VALIDATION_ERROR", status=422)
        setattr(org, field, value)
    if not (org.can_hire or org.can_provide):
        raise AppError(
            "Keep at least one of Hire workers or Provide work switched on.",
            code="CAPABILITY_REQUIRED",
            status=422,
        )
    if org.can_hire and not org.assistant_name:
        org.assistant_name = "Mira"
    await session.flush()
    return org
