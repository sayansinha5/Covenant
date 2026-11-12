"""`reconcile.run`: every 5 minutes (no payload) and on demand from Admin (`run_id`)."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs.base import JobContext, JobHandler, Payload
from app.services import reconcile


async def run(session: AsyncSession, ctx: JobContext, payload: Payload) -> None:
    # Each contract is checked in its own transaction, so this job doesn't use `session`.
    await reconcile.run(ctx.database, ctx.settings, ctx.paypal, payload.get("run_id"))


async def give_up(session: AsyncSession, ctx: JobContext, payload: Payload, error: str) -> None:
    await reconcile.mark_failed(session, payload.get("run_id"), error)


HANDLER = JobHandler(run=run, on_give_up=give_up)
