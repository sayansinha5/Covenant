"""A provider org for trying My workers. Onboarding is left unfinished on purpose.

The owner is Anika Desai. An older seed called this account Lipi Check; that name
is renamed here so it is not confused with the Lipi agent at Kabir Studio.

`python -m app.seed.lipi_studio`
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models import Membership, Organization, User
from app.seed.accounts import ensure_owner
from app.seed.run import run

EMAIL = "anika.desai@example.com"
OLD_EMAIL = "lipi.check@example.com"
PASSWORD = "correct horse battery 9"  # noqa: S105
FULL_NAME = "Anika Desai"
ORG_NAME = "Desai Studio"


async def seed(session: AsyncSession, _settings: Settings) -> str:
    renamed = await _rename_legacy(session)
    if renamed is not None:
        return renamed
    return await ensure_owner(
        session,
        email=EMAIL,
        password=PASSWORD,
        full_name=FULL_NAME,
        org_name=ORG_NAME,
        industry="software",
        can_hire=False,
        can_provide=True,
        onboarded=False,
    )


async def _rename_legacy(session: AsyncSession) -> str | None:
    """Move the old Lipi Check login onto Anika Desai when that address is still free."""
    current = await session.scalar(select(User).where(User.email == EMAIL))
    if current is not None:
        return None
    legacy = await session.scalar(select(User).where(User.email == OLD_EMAIL))
    if legacy is None:
        return None
    legacy.email = EMAIL
    legacy.full_name = FULL_NAME
    membership = await session.scalar(select(Membership).where(Membership.user_id == legacy.id))
    if membership is not None:
        org = await session.get(Organization, membership.org_id)
        if org is not None:
            org.name = ORG_NAME
    return f"Renamed {OLD_EMAIL} to {EMAIL} ({ORG_NAME})."


if __name__ == "__main__":
    run(seed)
