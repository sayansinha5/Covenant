"""`arbiter.verify`: score a delivery and hand the amounts to the settlement engine."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs.base import JobContext, JobHandler, Payload
from app.services import execution


async def run(session: AsyncSession, ctx: JobContext, payload: Payload) -> None:
    await execution.verify(session, ctx.settings, payload["contract_id"])


async def give_up(session: AsyncSession, ctx: JobContext, payload: Payload, error: str) -> None:
    await execution.give_up_verify(session, payload["contract_id"], error)


HANDLER = JobHandler(run=run, on_give_up=give_up)
