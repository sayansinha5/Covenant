from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.ids import uuid7
from app.domain.policy import WORK_TYPES, MandateTerms
from app.models import Mandate, Organization, User
from app.schemas.mandate import MandateCreate, MandateDefaults, MandateOut


async def active_mandate(session: AsyncSession, org_id: str) -> Mandate | None:
    return await session.scalar(
        select(Mandate).where(Mandate.org_id == org_id, Mandate.is_active.is_(True))
    )


def terms_of(mandate: Mandate | None) -> MandateTerms | None:
    if mandate is None:
        return None
    return MandateTerms(
        version=mandate.version,
        monthly_budget=mandate.monthly_budget,
        per_task_cap=mandate.per_task_cap,
        approval_threshold=mandate.approval_threshold,
        allowed_work_types=frozenset(mandate.allowed_work_types),
        is_active=mandate.is_active,
    )


def mandate_defaults(settings: Settings) -> MandateDefaults:
    return MandateDefaults(
        monthly_budget=settings.default_monthly_budget,
        per_task_cap=settings.default_per_task_cap,
        approval_threshold=settings.default_approval_threshold,
        allowed_work_types=list(WORK_TYPES),
    )


async def describe(session: AsyncSession, mandates: list[Mandate]) -> list[MandateOut]:
    signer_ids = {m.signed_by for m in mandates}
    rows = await session.execute(select(User.id, User.full_name).where(User.id.in_(signer_ids)))
    names = {row.id: row.full_name for row in rows}
    return [
        MandateOut(
            id=m.id,
            version=m.version,
            monthly_budget=m.monthly_budget,
            per_task_cap=m.per_task_cap,
            approval_threshold=m.approval_threshold,
            currency=m.currency,
            allowed_work_types=m.allowed_work_types,
            signed_by_name=names.get(m.signed_by, "Unknown"),
            signed_at=m.signed_at,
            is_active=m.is_active,
        )
        for m in mandates
    ]


async def list_versions(session: AsyncSession, org_id: str) -> list[Mandate]:
    return list(
        await session.scalars(
            select(Mandate).where(Mandate.org_id == org_id).order_by(Mandate.version.desc())
        )
    )


async def sign_mandate(
    session: AsyncSession, *, org_id: str, user_id: str, data: MandateCreate, currency: str
) -> Mandate:
    """Insert the next version and make it the only active one. The organization row lock
    serializes signing with funding, which reads the active mandate under the same lock."""
    await session.execute(
        select(Organization.id).where(Organization.id == org_id).with_for_update()
    )
    latest = await session.scalar(select(func.max(Mandate.version)).where(Mandate.org_id == org_id))
    await session.execute(
        update(Mandate)
        .where(Mandate.org_id == org_id, Mandate.is_active.is_(True))
        .values(is_active=False)
    )
    mandate = Mandate(
        id=uuid7(),
        org_id=org_id,
        version=(latest or 0) + 1,
        monthly_budget=data.monthly_budget,
        per_task_cap=data.per_task_cap,
        approval_threshold=data.approval_threshold,
        currency=currency,
        allowed_work_types=list(data.allowed_work_types),
        signed_by=user_id,
        is_active=True,
    )
    session.add(mandate)
    await session.flush()
    return mandate
