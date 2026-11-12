"""`webhook.process`: apply one verified PayPal webhook (see app/services/webhooks.py)."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs.base import JobContext, JobHandler, Payload
from app.services import webhooks


async def run(session: AsyncSession, ctx: JobContext, payload: Payload) -> None:
    await webhooks.process(session, ctx.settings, payload["webhook_event_id"])


async def give_up(session: AsyncSession, ctx: JobContext, payload: Payload, error: str) -> None:
    await webhooks.record_failure(session, payload["webhook_event_id"], error)


HANDLER = JobHandler(run=run, on_give_up=give_up)
