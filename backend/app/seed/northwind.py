"""Ada, hire and provide, already onboarded.

`python -m app.seed.northwind`
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.seed.accounts import ensure_owner
from app.seed.run import run

EMAIL = "ada+s5check@example.com"
PASSWORD = "correct horse battery 9"  # noqa: S105


async def seed(session: AsyncSession, _settings: Settings) -> str:
    return await ensure_owner(
        session,
        email=EMAIL,
        password=PASSWORD,
        full_name="Ada Tester",
        org_name="Northwind Test",
        industry="software",
        can_hire=True,
        can_provide=True,
        onboarded=True,
        assistant_name="Mira",
    )


if __name__ == "__main__":
    run(seed)
