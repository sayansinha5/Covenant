"""`worker.dispatch` and `worker.poll`: send a funded contract to its worker and follow up."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs.base import JobContext, JobHandler, Payload
from app.services import execution


async def run(session: AsyncSession, ctx: JobContext, payload: Payload) -> None:
    await execution.dispatch(session, ctx.settings, payload["contract_id"])


async def give_up(session: AsyncSession, ctx: JobContext, payload: Payload, error: str) -> None:
    await execution.give_up_dispatch(session, payload["contract_id"], error)


async def poll(session: AsyncSession, ctx: JobContext, payload: Payload) -> None:
    await execution.poll(
        session, ctx.settings, payload["contract_id"], str(payload.get("purpose") or "follow_up")
    )


HANDLER = JobHandler(run=run, on_give_up=give_up)
POLL_HANDLER = JobHandler(run=poll)
