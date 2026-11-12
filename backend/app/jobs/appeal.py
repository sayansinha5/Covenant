"""Appeal window, appeal memo and approval expiry. None of these calls PayPal itself."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs.base import JobContext, JobHandler, Payload
from app.services import execution


async def close_window(session: AsyncSession, ctx: JobContext, payload: Payload) -> None:
    await execution.close_appeal_window(session, ctx.settings, payload["contract_id"])


async def prepare(session: AsyncSession, ctx: JobContext, payload: Payload) -> None:
    await execution.prepare_appeal(session, ctx.settings, payload["contract_id"])


async def expire(session: AsyncSession, ctx: JobContext, payload: Payload) -> None:
    from app.services import hiring

    await hiring.expire_approval(session, payload["approval_id"])


CLOSE_HANDLER = JobHandler(run=close_window)
PREPARE_HANDLER = JobHandler(run=prepare)
EXPIRE_HANDLER = JobHandler(run=expire)
