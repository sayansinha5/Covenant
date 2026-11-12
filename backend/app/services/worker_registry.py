"""Register a worker and verify an agent against the fixed test task for its category.

The test delivery goes through the Arbiter. Registration uses the code judge (every item scores
10) so a pass means the hard checks and the manipulation scan passed, which is what a fixed
test task can prove without a second model call."""

import json
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.arbiter.pipeline import arbitrate, verification_spec
from app.core.config import Settings
from app.core.errors import AppError, ConflictError, NotFoundError
from app.core.ids import uuid7
from app.core.security import hash_token
from app.db.base import utcnow
from app.domain.state_machine import Job
from app.integrations.a2a.card import AgentCardInvalid, categories_of, parse_agent_card
from app.integrations.a2a.client import fetch_card, run_task
from app.integrations.a2a.ssrf import AgentUrlRefused, check_agent_url
from app.models import Worker, WorkerVerification
from app.services.outbox import enqueue

TASKS_PATH = Path(__file__).parents[1] / "seed" / "verification_tasks.json"
DEMO_TOKENS = {
    "lipi": "lipi_auth_token",
    "tally": "tally_auth_token",
    "quickwordz": "quickwordz_auth_token",
}


class AgentUrlRejected(AppError):
    status = 422
    code = "AGENT_URL_REJECTED"
    title = "Agent URL rejected"


def tasks() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(TASKS_PATH.read_text(encoding="utf-8"))
    return loaded


def bearer_token(settings: Settings, base_url: str, provided: str | None) -> str:
    if provided:
        return provided
    host = (urlparse(base_url).hostname or "").lower()
    configured = getattr(settings, DEMO_TOKENS[host], "") if host in DEMO_TOKENS else ""
    if configured:
        return str(configured)
    raise AppError(
        "Give the bearer token this agent expects.",
        status=422,
        code="AGENT_TOKEN_REQUIRED",
    )


async def register_agent(
    session: AsyncSession,
    settings: Settings,
    *,
    org_id: str,
    base_url: str,
    price: Decimal,
    currency: str,
    categories: list[str],
    auth_token: str | None,
) -> Worker:
    try:
        check_agent_url(base_url, settings.allowed_agent_hosts)
    except AgentUrlRefused as exc:
        raise AgentUrlRejected(str(exc)) from exc
    token = bearer_token(settings, base_url, auth_token)
    worker = Worker(
        id=uuid7(),
        org_id=org_id,
        kind="agent",
        display_name=base_url,
        base_url=base_url.rstrip("/"),
        categories=categories,
        price=price,
        currency=currency,
        status="pending",
        reputation=50,
        auth_token=token,
        auth_token_hash=hash_token(token),
    )
    session.add(worker)
    try:
        await session.flush()
    except IntegrityError:
        raise ConflictError(
            "An agent with this URL is already registered.", code="WORKER_URL_TAKEN"
        ) from None
    await _enqueue(session, worker.id)
    return worker


async def register_human(
    session: AsyncSession,
    *,
    org_id: str,
    display_name: str,
    description: str,
    price: Decimal,
    currency: str,
    categories: list[str],
) -> Worker:
    worker = Worker(
        id=uuid7(),
        org_id=org_id,
        kind="human",
        display_name=display_name,
        description=description,
        categories=categories,
        price=price,
        currency=currency,
        status="verified",
        reputation=50,
        verified_at=utcnow(),
    )
    session.add(worker)
    await session.flush()
    return worker


async def retry_verification(session: AsyncSession, *, org_id: str, worker_id: str) -> Worker:
    worker = await _owned(session, org_id, worker_id)
    if worker.kind != "agent":
        raise ConflictError("A person doesn't take the agent test.", code="NOT_AN_AGENT")
    if worker.status == "suspended":
        raise ConflictError("Suspended workers can't be re-verified.", code="WORKER_SUSPENDED")
    worker.status = "pending"
    await session.execute(
        delete(WorkerVerification).where(WorkerVerification.worker_id == worker.id)
    )
    await _enqueue(session, worker.id)
    return worker


async def verify(session: AsyncSession, settings: Settings, worker_id: str) -> None:
    """One verification attempt. A refusal or a failed check finishes the job; a network
    problem is raised so the runner tries again."""
    worker = await session.get(Worker, worker_id)
    if worker is None or worker.kind != "agent" or worker.status == "verified":
        return
    if worker.base_url is None or worker.auth_token is None:
        await _fail(session, worker, "agent_card", "This agent has no URL.")
        return
    try:
        card = parse_agent_card(await fetch_card(settings, worker.base_url))
    except AgentCardInvalid as exc:
        await _fail(session, worker, "agent_card", str(exc))
        return
    worker.display_name = card.name
    worker.description = card.description
    worker.agent_card = {
        "name": card.name,
        "description": card.description,
        "url": card.url,
        "version": card.version,
        "protocol_version": card.protocol_version,
        "skills": list(card.skills),
    }
    await _step(session, worker.id, "agent_card", f"Read {card.name} ({card.protocol_version}).")
    offered = set(categories_of(card))
    missing = [category for category in worker.categories if category not in offered]
    if missing:
        await _fail(
            session,
            worker,
            "skills",
            "The agent doesn't offer "
            f"{', '.join(missing)}. Its tags: {', '.join(sorted(offered)) or 'none'}.",
        )
        return
    await _step(session, worker.id, "skills", f"Offers {', '.join(worker.categories)}.")
    category = worker.categories[0]
    task = tasks()[category]
    payload = {
        "kind": "verification",
        "category": category,
        "instructions": task["instructions"],
        "items": task["items"],
    }
    delivery = await run_task(settings, worker.base_url, worker.auth_token, payload)
    await _step(session, worker.id, "test_job", "The test job came back.")
    draft = await arbitrate(
        settings,
        spec=verification_spec(settings, task),
        delivery=delivery,
        source_items=list(task["items"]),
        use_model=False,
    )
    if draft.result != "pass":
        await _fail(session, worker, "checks", draft.reasoning[:500])
        return
    worker.status = "verified"
    worker.verified_at = utcnow()
    worker.reputation = 50
    await _step(session, worker.id, "checks", "The test delivery passed.")


async def give_up(session: AsyncSession, worker_id: str, error: str) -> None:
    worker = await session.get(Worker, worker_id)
    if worker is None or worker.status == "verified":
        return
    await _fail(session, worker, "test_job", error[:500])


async def _enqueue(session: AsyncSession, worker_id: str) -> None:
    await enqueue(
        session,
        Job.VERIFY_WORKER,
        {"worker_id": worker_id},
        dedupe_key=f"worker.verify:{worker_id}:{uuid7()}",
        max_attempts=3,
    )


async def _owned(session: AsyncSession, org_id: str, worker_id: str) -> Worker:
    worker = await session.get(Worker, worker_id)
    if worker is None or worker.org_id != org_id:
        raise NotFoundError("This worker doesn't exist.", code="WORKER_NOT_FOUND")
    return worker


async def _fail(session: AsyncSession, worker: Worker, step: str, detail: str) -> None:
    worker.status = "failed"
    await _step(session, worker.id, step, detail, result="failed")


async def _step(
    session: AsyncSession, worker_id: str, step: str, detail: str, *, result: str = "ok"
) -> None:
    session.add(
        WorkerVerification(id=uuid7(), worker_id=worker_id, step=step, result=result, detail=detail)
    )


async def verification_steps(session: AsyncSession, worker_id: str) -> list[WorkerVerification]:
    return list(
        await session.scalars(
            select(WorkerVerification)
            .where(WorkerVerification.worker_id == worker_id)
            .order_by(WorkerVerification.created_at)
        )
    )
