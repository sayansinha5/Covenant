"""Platform admin. `python -m app.seed.admin`"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.security import hash_password
from app.db.base import utcnow
from app.models import Membership, Organization, User
from app.seed.run import run

ADMIN_ORG_NAME = "Covenant Operations"


async def seed_admin(session: AsyncSession, settings: Settings) -> str:
    """The platform admin, owner of an operations organization that neither hires nor provides
    (so the app shell has an organization to show). An existing admin keeps their password."""
    email = settings.seed_admin_email.lower()
    user = await session.scalar(select(User).where(User.email == email))
    if user is not None:
        user.is_platform_admin = True
        return f"Admin {email} already exists (password unchanged)."
    user = User(
        email=email,
        password_hash=hash_password(settings.seed_admin_password.get_secret_value()),
        full_name="Covenant Admin",
        is_platform_admin=True,
    )
    org = Organization(
        name=ADMIN_ORG_NAME,
        industry="software",
        country="IN",
        can_hire=False,
        can_provide=False,
        onboarded_at=utcnow(),
    )
    session.add_all([user, org])
    await session.flush()
    session.add(Membership(user_id=user.id, org_id=org.id, role="owner"))
    return f"Created admin {email} (password from SEED_ADMIN_PASSWORD)."


if __name__ == "__main__":
    run(seed_admin)
