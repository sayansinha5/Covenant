"""Kabir's studio and the three demo agents, when their URLs are still free.

python -m app.seed.kabir
"""

import os
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.base import utcnow
from app.models import Membership, Organization, User, Worker
from app.seed.accounts import ensure_owner
from app.seed.run import run

PASSWORD = "studio looms 2026"  # noqa: S105


async def seed_kabir(session: AsyncSession, _settings: Settings) -> str:
    account = await ensure_owner(
        session,
        email="kabir@studio.example",
        password=PASSWORD,
        full_name="Kabir Shah",
        org_name="Kabir Studio",
        industry="services",
        can_hire=False,
        can_provide=True,
        onboarded=False,
    )
    user = await session.scalar(select(User).where(User.email == "kabir@studio.example"))
    if user is None:
        return account
    membership = await session.scalar(select(Membership).where(Membership.user_id == user.id))
    if membership is None:
        return account
    org = await session.get(Organization, membership.org_id)
    if org is None:
        return account
    lines = [account]
    workers = (
        ("Lipi", "LIPI_PUBLIC_URL", "http://127.0.0.1:9101", Decimal("40.00"), "translation"),
        ("Tally", "TALLY_PUBLIC_URL", "http://127.0.0.1:9102", Decimal("30.00"), "catalog_data"),
        (
            "QuickWordz",
            "QUICKWORDZ_PUBLIC_URL",
            "http://127.0.0.1:9103",
            Decimal("25.00"),
            "copywriting",
        ),
    )
    for name, env_name, default, price, category in workers:
        url = os.environ.get(env_name, default)
        lines.append(await _ensure_agent(session, org.id, name, url, price, category))
    return " ".join(lines)


async def _ensure_agent(
    session: AsyncSession, org_id: str, name: str, url: str, price: Decimal, category: str
) -> str:
    existing = await session.scalar(select(Worker).where(Worker.base_url == url))
    if existing is not None:
        return f"{name} already registered."
    session.add(
        Worker(
            org_id=org_id,
            kind="agent",
            display_name=name,
            description=f"{name} demo worker.",
            base_url=url,
            categories=[category],
            price=price,
            currency="USD",
            status="verified",
            reputation=50,
            verified_at=utcnow(),
        )
    )
    return f"Registered {name}."


if __name__ == "__main__":
    run(seed_kabir)
