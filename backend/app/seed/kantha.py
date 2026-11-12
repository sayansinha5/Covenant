"""Riya, hire only. Onboarding is left unfinished on purpose.

`python -m app.seed.kantha`
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.seed.accounts import ensure_owner
from app.seed.run import run

EMAIL = "riya+482917@kantha.example"
PASSWORD = "kantha stoles 2026"  # noqa: S105


async def seed(session: AsyncSession, _settings: Settings) -> str:
    return await ensure_owner(
        session,
        email=EMAIL,
        password=PASSWORD,
        full_name="Riya Sen",
        org_name="Kantha & Co.",
        industry="retail_handicrafts",
        can_hire=True,
        can_provide=False,
        onboarded=False,
        assistant_name="Mira",
    )


if __name__ == "__main__":
    run(seed)
