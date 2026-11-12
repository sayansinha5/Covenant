"""Create one owner and their organization. An existing email is left alone."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.db.base import utcnow
from app.models import Membership, Organization, User


async def ensure_owner(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    full_name: str,
    org_name: str,
    industry: str,
    can_hire: bool,
    can_provide: bool,
    onboarded: bool,
    assistant_name: str | None = None,
    is_platform_admin: bool = False,
) -> str:
    address = email.lower()
    existing = await session.scalar(select(User).where(User.email == address))
    if existing is not None:
        return f"{address} already exists (password unchanged)."
    user = User(
        email=address,
        password_hash=hash_password(password),
        full_name=full_name,
        is_platform_admin=is_platform_admin,
    )
    org = Organization(
        name=org_name,
        industry=industry,
        country="IN",
        can_hire=can_hire,
        can_provide=can_provide,
        assistant_name=assistant_name,
        onboarded_at=utcnow() if onboarded else None,
    )
    session.add_all([user, org])
    await session.flush()
    session.add(Membership(user_id=user.id, org_id=org.id, role="owner"))
    return f"Created {address} ({org_name})."
