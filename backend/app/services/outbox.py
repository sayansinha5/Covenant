from datetime import datetime
from typing import Any

from sqlalchemy.dialects.mysql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ids import uuid7
from app.db.base import utcnow
from app.models import OutboxJob

DEFAULT_MAX_ATTEMPTS = 6


async def enqueue(
    session: AsyncSession,
    kind: str,
    payload: dict[str, Any],
    *,
    dedupe_key: str,
    run_after: datetime | None = None,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> None:
    """Add a job in the caller's transaction, so it exists only if the caller commits.

    A job with the same `dedupe_key` is left untouched: enqueueing twice (a retried request,
    a duplicate webhook) still runs the work once."""
    now = utcnow()
    statement = insert(OutboxJob).values(
        id=uuid7(),
        kind=kind,
        payload=payload,
        dedupe_key=dedupe_key,
        status="queued",
        attempts=0,
        max_attempts=max_attempts,
        run_after=run_after or now,
        created_at=now,
        updated_at=now,
    )
    await session.execute(
        statement.on_duplicate_key_update(dedupe_key=statement.inserted.dedupe_key)
    )
