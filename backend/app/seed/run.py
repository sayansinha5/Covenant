"""Run one seed function in its own transaction. Each `python -m app.seed.<name>` uses this."""

import asyncio
import sys
from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import ConfigurationError, Settings, load_settings
from app.db.engine import Database

Seed = Callable[[AsyncSession, Settings], Awaitable[str]]


def run(seed: Seed) -> None:
    try:
        settings = load_settings()
    except ConfigurationError as exc:
        print(f"Covenant seed cannot run.\n{exc}", file=sys.stderr)  # noqa: T201
        raise SystemExit(1) from None

    async def execute() -> None:
        database = Database.from_settings(settings)
        try:
            async with database.session() as session, session.begin():
                print(await seed(session, settings))  # noqa: T201
        finally:
            await database.dispose()

    asyncio.run(execute())
