"""`worker.verify`: fetch the agent card, run the category's test task and record the result."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs.base import JobContext, JobHandler, Payload
from app.services import worker_registry


async def run(session: AsyncSession, ctx: JobContext, payload: Payload) -> None:
    await worker_registry.verify(session, ctx.settings, payload["worker_id"])


async def give_up(session: AsyncSession, ctx: JobContext, payload: Payload, error: str) -> None:
    await worker_registry.give_up(session, payload["worker_id"], error)


HANDLER = JobHandler(run=run, on_give_up=give_up)
