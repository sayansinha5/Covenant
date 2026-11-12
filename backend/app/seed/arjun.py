"""Arjun, a human designer. Run: python -m app.seed.arjun"""

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.base import utcnow
from app.models import Membership, Organization, User, Worker
from app.seed.accounts import ensure_owner
from app.seed.run import run

PASSWORD = "kantha motifs 2026"  # noqa: S105


async def seed_arjun(session: AsyncSession, _settings: Settings) -> str:
    account = await ensure_owner(
        session,
        email="arjun@design.example",
        password=PASSWORD,
        full_name="Arjun Nair",
        org_name="Arjun Nair Design",
        industry="media",
        can_hire=False,
        can_provide=True,
        onboarded=False,
    )
    user = await session.scalar(select(User).where(User.email == "arjun@design.example"))
    if user is None:
        return account
    membership = await session.scalar(select(Membership).where(Membership.user_id == user.id))
    if membership is None:
        return account
    org = await session.get(Organization, membership.org_id)
    if org is None:
        return account
    existing = await session.scalar(
        select(Worker).where(Worker.org_id == org.id, Worker.display_name == "Arjun")
    )
    if existing is not None:
        return f"{account} Arjun already listed."
    session.add(
        Worker(
            org_id=org.id,
            kind="human",
            display_name="Arjun",
            description="Logos and motifs, including kantha stitch.",
            categories=["design"],
            price=Decimal("55.00"),
            currency="USD",
            status="verified",
            reputation=50,
            verified_at=utcnow(),
        )
    )
    return f"{account} Listed Arjun at $55."


if __name__ == "__main__":
    run(seed_arjun)
