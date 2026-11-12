"""Move a contract from funded to settled: dispatch, poll, the Arbiter, appeals.

Money amounts come from `begin_settlement`. This module never sends a number a model produced
to PayPal."""

from datetime import timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.arbiter.decide import money_band
from app.ai.arbiter.pipeline import VerdictDraft, arbitrate
from app.ai.factory import AINotConfigured, Tier, get_chat_model, get_second_opinion_model
from app.ai.prompts import load_prompt
from app.ai.spotlight import spotlight
from app.ai.structured import StructuredOutputFailed, invoke_structured
from app.ai.tracing import run_config
from app.core.config import Settings
from app.core.errors import ConflictError
from app.core.ids import uuid7
from app.db.base import utcnow
from app.domain.reputation import counts_as_completed, next_reputation, suspension_reason
from app.domain.settlement import Band
from app.domain.state_machine import Event, Job, State
from app.integrations.a2a.client import AgentCallError, run_task
from app.jobs.base import RetryLater
from app.models import Appeal, Contract, Delivery, Verdict, Worker
from app.services.contracts import SYSTEM, Actor, ContractNotFound, lock_contract, note, transition
from app.services.escrow import begin_settlement, lock_org
from app.services.notify import notify
from app.services.outbox import enqueue

POLL_SECONDS = 5
APPEAL_MIN_CHARS = 50


async def dispatch(session: AsyncSession, settings: Settings, contract_id: str) -> None:
    """Send a funded contract to its worker. Agents are called over A2A; humans get an offer."""
    contract = await _system_lock(session, contract_id)
    if contract is None or contract.state not in (State.FUNDED, State.SENT_TO_WORKER):
        return
    worker = await session.get(Worker, contract.worker_id)
    if worker is None:
        return
    _stamp_deadlines(contract, settings, worker)
    if contract.state == State.FUNDED:
        await transition(
            session,
            contract,
            Event.DISPATCHED,
            actor=SYSTEM,
            message=f"Sent to {worker.display_name}.",
        )
        notify(
            session,
            org_id=contract.provider_org_id,
            kind="offer",
            title=f"New offer: {contract.title}",
            body=f"A hirer sent {worker.display_name} a contract.",
            link=f"/contracts/{contract.id}",
        )
    if worker.kind == "human":
        await _enqueue_poll(session, contract, "accept_timeout", contract.accept_by_at)
        return
    if await _latest_delivery(session, contract.id) is None:
        await _call_agent(session, settings, contract, worker)
    await _finish_agent_delivery(session, contract, worker)
    await _enqueue_poll(session, contract, "follow_up", utcnow() + timedelta(seconds=POLL_SECONDS))


async def poll(session: AsyncSession, settings: Settings, contract_id: str, purpose: str) -> None:
    """Follow up a dispatch: time out an unanswered offer, or finish a delivery dispatch stored."""
    contract = await _system_lock(session, contract_id)
    if contract is None:
        return
    now = utcnow()
    if (
        purpose == "accept_timeout"
        and contract.state == State.SENT_TO_WORKER
        and contract.accept_by_at is not None
        and contract.accept_by_at <= now
    ):
        await transition(
            session,
            contract,
            Event.ACCEPT_TIMEOUT,
            actor=SYSTEM,
            message="The worker didn't accept in time. Releasing the hold.",
        )
        return
    if (
        contract.state == State.IN_PROGRESS
        and contract.deadline_at is not None
        and contract.deadline_at <= now
        and await _latest_delivery(session, contract.id) is None
    ):
        await transition(
            session,
            contract,
            Event.DEADLINE_MISSED,
            actor=SYSTEM,
            message="The deadline passed before a delivery arrived. Releasing the hold.",
        )
        return
    if contract.state != State.SENT_TO_WORKER:
        return
    worker = await session.get(Worker, contract.worker_id)
    if worker is None or worker.kind != "agent" or worker.base_url is None:
        return
    if await _latest_delivery(session, contract.id) is None:
        await _call_agent(session, settings, contract, worker)
    await _finish_agent_delivery(session, contract, worker)


async def give_up_dispatch(session: AsyncSession, contract_id: str, error: str) -> None:
    contract = await _system_lock(session, contract_id)
    if contract is None:
        return
    if contract.state == State.FUNDED:
        await transition(
            session,
            contract,
            Event.DISPATCHED,
            actor=SYSTEM,
            message="Couldn't reach the worker.",
            data={"error": error[:300]},
        )
    if contract.state == State.SENT_TO_WORKER:
        await transition(
            session,
            contract,
            Event.WORKER_DECLINED,
            actor=SYSTEM,
            message="The worker didn't complete the task. Releasing the hold.",
            data={"error": error[:300]},
        )


async def verify(session: AsyncSession, settings: Settings, contract_id: str) -> None:
    """Run the Arbiter, store the verdict, and settle agents immediately."""
    contract = await _system_lock(session, contract_id)
    if contract is None or contract.state != State.VERIFYING:
        return
    delivery = await _latest_delivery(session, contract.id)
    if delivery is None:
        await transition(
            session,
            contract,
            Event.VERIFY_GAVE_UP,
            actor=SYSTEM,
            message="There is no delivery to verify.",
        )
        return
    verdict = await session.scalar(select(Verdict).where(Verdict.delivery_id == delivery.id))
    if verdict is None:
        draft = await arbitrate(
            settings,
            spec=contract.spec or {},
            delivery=delivery.content,
            source_items=list(contract.source_items or []),
            contract_id=contract.id,
            org_id=contract.hirer_org_id,
        )
        verdict = _verdict_row(contract.id, delivery.id, draft)
        session.add(verdict)
        await session.flush()
        await _apply_reputation(session, contract.worker_id, draft.result)
    await transition(
        session,
        contract,
        Event.VERDICT_READY,
        actor=SYSTEM,
        message=_verdict_message(verdict),
        data={"result": verdict.result, "pass_ratio": str(verdict.pass_ratio)},
    )
    notify(
        session,
        org_id=contract.hirer_org_id,
        kind="verdict",
        title=f"Verdict on {contract.title}",
        body=_verdict_message(verdict),
        link=f"/contracts/{contract.id}",
    )
    notify(
        session,
        org_id=contract.provider_org_id,
        kind="verdict",
        title=f"Verdict on {contract.title}",
        body=_verdict_message(verdict),
        link=f"/contracts/{contract.id}",
    )
    await _settle_or_wait(session, settings, contract, verdict)


async def give_up_verify(session: AsyncSession, contract_id: str, error: str) -> None:
    contract = await _system_lock(session, contract_id)
    if contract is None or contract.state != State.VERIFYING:
        return
    await transition(
        session,
        contract,
        Event.VERIFY_GAVE_UP,
        actor=SYSTEM,
        message="Verification didn't finish. An admin will look at it.",
        data={"error": error[:300]},
    )


async def close_appeal_window(session: AsyncSession, settings: Settings, contract_id: str) -> None:
    contract = await _system_lock(session, contract_id)
    if contract is None or contract.state != State.VERDICT_ISSUED:
        return
    if contract.appeal_window_ends_at and contract.appeal_window_ends_at > utcnow():
        remaining = (contract.appeal_window_ends_at - utcnow()).total_seconds()
        raise RetryLater("The appeal window is still open.", delay_seconds=max(remaining, 1))
    verdict = await _latest_verdict(session, contract.id)
    if verdict is None or money_band(verdict.result) is None:
        return
    await _settle(session, settings, contract, verdict, Event.APPEAL_WINDOW_CLOSED)


async def prepare_appeal(session: AsyncSession, settings: Settings, contract_id: str) -> None:
    """An advisory memo for the hirer. It never settles the contract."""
    appeal = await session.scalar(
        select(Appeal).where(Appeal.contract_id == contract_id).order_by(Appeal.created_at.desc())
    )
    if appeal is None or appeal.memo is not None:
        return
    verdict = await session.get(Verdict, appeal.verdict_id)
    if verdict is None:
        return
    appeal.memo = await _memo(settings, verdict, appeal.argument, contract_id)
    appeal.status = "memo_ready"
    contract = await session.get(Contract, contract_id)
    if contract is not None:
        notify(
            session,
            org_id=contract.hirer_org_id,
            kind="appeal",
            title=f"Appeal ready: {contract.title}",
            body="A decision memo is ready. You choose whether to accept the appeal.",
            link=f"/contracts/{contract.id}",
        )


async def accept_offer(
    session: AsyncSession, *, org_id: str, contract_id: str, actor: Actor, actor_name: str
) -> Contract:
    contract = await _party_lock(session, contract_id, org_id, side="provider")
    if contract.state != State.SENT_TO_WORKER:
        raise ConflictError("This offer isn't waiting for you.", code="INVALID_TRANSITION")
    await transition(
        session,
        contract,
        Event.WORKER_ACCEPTED,
        actor=actor,
        message=f"{actor_name} accepted the offer.",
    )
    if contract.deadline_at is not None:
        await _enqueue_poll(session, contract, "deadline", contract.deadline_at)
    return contract


async def decline_offer(
    session: AsyncSession, *, org_id: str, contract_id: str, actor: Actor, actor_name: str
) -> Contract:
    contract = await _party_lock(session, contract_id, org_id, side="provider")
    if contract.state != State.SENT_TO_WORKER:
        raise ConflictError("This offer isn't waiting for you.", code="INVALID_TRANSITION")
    await transition(
        session,
        contract,
        Event.WORKER_DECLINED,
        actor=actor,
        message=f"{actor_name} declined the offer. Releasing the hold.",
    )
    return contract


async def submit_delivery(
    session: AsyncSession,
    *,
    org_id: str,
    contract_id: str,
    actor: Actor,
    actor_name: str,
    content: Any,
    file_ids: list[str] | None,
) -> Contract:
    contract = await _party_lock(session, contract_id, org_id, side="provider")
    if contract.state != State.IN_PROGRESS:
        raise ConflictError(
            "This contract isn't waiting for a delivery.", code="INVALID_TRANSITION"
        )
    late = contract.deadline_at is not None and contract.deadline_at <= utcnow()
    session.add(
        Delivery(
            id=uuid7(),
            contract_id=contract.id,
            submitted_by=org_id,
            content=content,
            file_ids=file_ids,
            is_late=late,
        )
    )
    await transition(
        session,
        contract,
        Event.DELIVERED,
        actor=actor,
        message=f"{actor_name} submitted a delivery.",
        data={"late": late},
    )
    return contract


async def open_appeal(
    session: AsyncSession, *, org_id: str, contract_id: str, actor: Actor, argument: str
) -> Appeal:
    if len(argument.strip()) < APPEAL_MIN_CHARS:
        raise ConflictError(
            f"Write at least {APPEAL_MIN_CHARS} characters so the hirer can judge the appeal.",
            code="APPEAL_TOO_SHORT",
        )
    contract = await _party_lock(session, contract_id, org_id, side="provider")
    if contract.state != State.VERDICT_ISSUED:
        raise ConflictError("This verdict can't be appealed now.", code="INVALID_TRANSITION")
    if contract.appeal_window_ends_at and contract.appeal_window_ends_at <= utcnow():
        raise ConflictError("The appeal window has closed.", code="APPEAL_CLOSED")
    verdict = await _latest_verdict(session, contract.id)
    if verdict is None:
        raise ConflictError("There's no verdict to appeal.", code="INVALID_TRANSITION")
    appeal = Appeal(
        id=uuid7(), contract_id=contract.id, verdict_id=verdict.id, argument=argument.strip()
    )
    session.add(appeal)
    await transition(
        session,
        contract,
        Event.APPEAL_OPENED,
        actor=actor,
        message="The worker appealed the verdict.",
    )
    return appeal


async def accept_verdict(
    session: AsyncSession,
    settings: Settings,
    *,
    org_id: str,
    contract_id: str,
    actor: Actor,
    actor_name: str,
) -> Contract:
    contract = await _party_lock(session, contract_id, org_id, side="provider")
    if contract.state != State.VERDICT_ISSUED:
        raise ConflictError("There's no open verdict to accept.", code="INVALID_TRANSITION")
    verdict = await _latest_verdict(session, contract.id)
    if verdict is None or money_band(verdict.result) is None:
        raise ConflictError("A person still needs to choose the payment band.", code="NEEDS_REVIEW")
    await _settle(
        session,
        settings,
        contract,
        verdict,
        Event.WORKER_ACCEPTED_VERDICT,
        actor,
        message=f"{actor_name} accepted the verdict.",
    )
    return contract


async def choose_band(
    session: AsyncSession,
    settings: Settings,
    *,
    org_id: str,
    contract_id: str,
    band: str,
    actor: Actor,
    actor_name: str,
) -> Contract:
    contract = await _party_lock(session, contract_id, org_id, side="hirer")
    if contract.state != State.VERDICT_ISSUED:
        raise ConflictError(
            "This contract isn't waiting for a decision.", code="INVALID_TRANSITION"
        )
    verdict = await _latest_verdict(session, contract.id)
    if verdict is None or verdict.result != "needs_review":
        raise ConflictError("This verdict doesn't need a band chosen.", code="INVALID_TRANSITION")
    chosen = money_band(band)
    if chosen is None:
        raise ConflictError("Choose pass, partial or fail.", code="BAD_REQUEST")
    ratio = verdict.pass_ratio if chosen is Band.PARTIAL else Decimal("1")
    await begin_settlement(
        session,
        settings,
        contract,
        Event.HIRER_DECIDED_BAND,
        chosen,
        pass_ratio=ratio,
        actor=actor,
        message=f"{actor_name} chose to {chosen.value} this contract.",
    )
    return contract


async def decide_appeal(
    session: AsyncSession,
    settings: Settings,
    *,
    org_id: str,
    contract_id: str,
    accept: bool,
    actor: Actor,
    actor_name: str,
    note_text: str | None,
) -> Contract:
    """Accepting an appeal captures the full hold. Upholding settles the original band."""
    contract = await _party_lock(session, contract_id, org_id, side="hirer")
    if contract.state != State.UNDER_APPEAL:
        raise ConflictError("This contract isn't under appeal.", code="INVALID_TRANSITION")
    verdict = await _latest_verdict(session, contract.id)
    appeal = await session.scalar(
        select(Appeal).where(Appeal.contract_id == contract.id).order_by(Appeal.created_at.desc())
    )
    if verdict is None or appeal is None:
        raise ConflictError("The appeal record is missing.", code="INVALID_TRANSITION")
    if accept:
        band, ratio, event = Band.PASS, Decimal("1"), Event.APPEAL_ACCEPTED
        appeal.status = "accepted"
        message = f"{actor_name} accepted the appeal. Capturing the full hold."
    else:
        band = money_band(verdict.result) or Band.FAIL
        ratio, event = verdict.pass_ratio, Event.APPEAL_UPHELD
        appeal.status = "upheld"
        message = f"{actor_name} upheld the verdict."
    appeal.decision_note = (note_text or "")[:500] or None
    appeal.decided_at = utcnow()
    await begin_settlement(
        session,
        settings,
        contract,
        event,
        band,
        pass_ratio=ratio,
        actor=actor,
        message=message,
    )
    return contract


async def _call_agent(
    session: AsyncSession, settings: Settings, contract: Contract, worker: Worker
) -> None:
    if worker.base_url is None or worker.auth_token is None:
        raise AgentCallError("This agent has no URL.")
    try:
        content = await run_task(settings, worker.base_url, worker.auth_token, _task(contract))
    except AgentCallError as exc:
        if _retryable(exc):
            raise
        await transition(
            session,
            contract,
            Event.WORKER_DECLINED,
            actor=SYSTEM,
            message="The worker rejected the task. Releasing the hold.",
            data={"error": str(exc)[:300]},
        )
        return
    late = contract.deadline_at is not None and contract.deadline_at <= utcnow()
    session.add(
        Delivery(
            id=uuid7(),
            contract_id=contract.id,
            submitted_by=worker.id,
            content=content,
            is_late=late,
        )
    )
    await session.flush()


async def _finish_agent_delivery(session: AsyncSession, contract: Contract, worker: Worker) -> None:
    if await _latest_delivery(session, contract.id) is None:
        return
    if contract.state == State.SENT_TO_WORKER:
        await transition(
            session,
            contract,
            Event.WORKER_ACCEPTED,
            actor=Actor("worker", worker.id),
            message=f"{worker.display_name} accepted the work.",
        )
    if contract.state == State.IN_PROGRESS:
        await transition(
            session,
            contract,
            Event.DELIVERED,
            actor=Actor("worker", worker.id),
            message=f"{worker.display_name} delivered the work.",
        )


async def _settle_or_wait(
    session: AsyncSession, settings: Settings, contract: Contract, verdict: Verdict
) -> None:
    if contract.state != State.VERDICT_ISSUED or money_band(verdict.result) is None:
        if verdict.result == "needs_review":
            note(
                session,
                contract,
                "The two reviews disagreed. Choose a payment band to settle.",
                actor=SYSTEM,
            )
        return
    worker = await session.get(Worker, contract.worker_id)
    if worker is not None and worker.kind == "human":
        window = utcnow() + timedelta(minutes=settings.appeal_window_minutes)
        contract.appeal_window_ends_at = window
        note(
            session,
            contract,
            "Appeal window open. The worker can appeal or accept the verdict.",
            actor=SYSTEM,
        )
        await enqueue(
            session,
            Job.CLOSE_APPEAL,
            {"contract_id": contract.id},
            dedupe_key=f"{Job.CLOSE_APPEAL}:{contract.id}",
            run_after=window,
        )
        return
    await _settle(session, settings, contract, verdict, Event.SETTLE)


async def _settle(
    session: AsyncSession,
    settings: Settings,
    contract: Contract,
    verdict: Verdict,
    event: Event,
    actor: Actor = SYSTEM,
    message: str | None = None,
) -> None:
    band = money_band(verdict.result)
    if band is None or contract.state != State.VERDICT_ISSUED:
        return
    await begin_settlement(
        session,
        settings,
        contract,
        event,
        band,
        pass_ratio=verdict.pass_ratio,
        actor=actor,
        message=message or _verdict_message(verdict),
    )


def _stamp_deadlines(contract: Contract, settings: Settings, worker: Worker) -> None:
    now = utcnow()
    spec = contract.spec or {}
    if contract.deadline_at is None:
        minutes = int(spec.get("deadline_minutes") or 0)
        if minutes <= 0:
            minutes = (
                int(settings.agent_default_deadline_minutes)
                if worker.kind == "agent"
                else int(settings.human_default_deadline_hours * 60)
            )
        contract.deadline_at = now + timedelta(minutes=minutes)
    if contract.accept_by_at is None:
        if worker.kind == "agent":
            contract.accept_by_at = now + timedelta(minutes=settings.agent_accept_timeout_minutes)
        else:
            contract.accept_by_at = now + timedelta(hours=settings.human_accept_timeout_hours)


def _task(contract: Contract) -> dict[str, Any]:
    spec = contract.spec or {}
    deadline = contract.deadline_at.isoformat() if contract.deadline_at else None
    return {
        "kind": "contract",
        "contract_number": f"C-{contract.number}",
        "spec_hash": contract.spec_hash,
        "deadline": deadline,
        "instructions": spec.get("deliverable_description") or contract.request_text,
        "items": list(contract.source_items or [{"text": contract.request_text}]),
    }


def _verdict_row(contract_id: str, delivery_id: str, draft: VerdictDraft) -> Verdict:
    return Verdict(
        id=uuid7(),
        contract_id=contract_id,
        delivery_id=delivery_id,
        result=draft.result,
        pass_ratio=draft.pass_ratio,
        overall_score=Decimal(str(draft.overall_score)).quantize(Decimal("0.01")),
        item_results=draft.item_results,
        manipulation=draft.manipulation,
        reasoning=draft.reasoning,
        judge_model=draft.judge_model,
        second_opinion=draft.second_opinion,
        prompt_version=draft.prompt_version,
        langsmith_run_id=draft.langsmith_run_id,
    )


def _verdict_message(verdict: Verdict) -> str:
    if verdict.result == "pass":
        return "The delivery passed."
    if verdict.result == "partial":
        return f"Partial delivery: {verdict.pass_ratio:.0%} of items passed."
    if verdict.result == "manipulation":
        return "The delivery tried to influence the review."
    if verdict.result == "needs_review":
        return "The reviews disagreed. A person needs to choose the band."
    return "The delivery didn't pass."


async def _apply_reputation(session: AsyncSession, worker_id: str, result: str) -> None:
    worker = await session.get(Worker, worker_id)
    if worker is None:
        return
    worker.reputation = next_reputation(worker.reputation, result)
    if counts_as_completed(result):
        worker.jobs_completed += 1
    if reason := suspension_reason(result):
        worker.status = "suspended"
        worker.suspended_reason = reason


async def _memo(
    settings: Settings, verdict: Verdict, argument: str, contract_id: str
) -> dict[str, Any]:
    fallback = {
        "summary": verdict.reasoning,
        "recommendation": "uphold",
        "assessment": "This memo restates the verdict for the hirer to decide.",
        "confidence": 1,
    }
    if not settings.ai_configured:
        return fallback
    try:
        prompt = load_prompt("appeal")
        block = spotlight("argument", argument)
        traced = run_config(
            settings,
            component="appeal",
            prompt_version=prompt.version_id,
            contract_id=contract_id,
        )
        from pydantic import BaseModel, Field

        class Memo(BaseModel):
            summary: str
            recommendation: str
            assessment: str
            confidence: float = Field(ge=0, le=1)

        written = await invoke_structured(
            get_chat_model(settings, Tier.REASONING),
            Memo,
            prompt.messages(
                verdict=verdict.reasoning,
                argument=block.block,
            ),
            config=traced.config,
            validate=lambda parsed: parsed,
        )
        second = None
        try:
            other = await invoke_structured(
                get_second_opinion_model(settings),
                Memo,
                prompt.messages(verdict=verdict.reasoning, argument=block.block),
                config=traced.config,
                validate=lambda parsed: parsed,
            )
            second = other.model_dump()
        except (AINotConfigured, StructuredOutputFailed):
            second = None
        return {
            **written.model_dump(),
            "second_opinion": second,
            "prompt_version": prompt.version_id,
        }
    except (AINotConfigured, StructuredOutputFailed):
        return fallback


async def _latest_delivery(session: AsyncSession, contract_id: str) -> Delivery | None:
    return await session.scalar(
        select(Delivery)
        .where(Delivery.contract_id == contract_id)
        .order_by(Delivery.received_at.desc())
    )


async def _latest_verdict(session: AsyncSession, contract_id: str) -> Verdict | None:
    return await session.scalar(
        select(Verdict)
        .where(Verdict.contract_id == contract_id)
        .order_by(Verdict.created_at.desc())
    )


async def _system_lock(session: AsyncSession, contract_id: str) -> Contract | None:
    contract = await session.get(Contract, contract_id)
    if contract is None:
        return None
    await lock_org(session, contract.hirer_org_id)
    return await lock_contract(session, contract_id)


async def _party_lock(
    session: AsyncSession, contract_id: str, org_id: str, *, side: str
) -> Contract:
    contract = await session.get(Contract, contract_id)
    if contract is None:
        raise ContractNotFound
    owns = contract.hirer_org_id if side == "hirer" else contract.provider_org_id
    if owns != org_id:
        raise ContractNotFound
    await lock_org(session, contract.hirer_org_id)
    return await lock_contract(session, contract_id)


async def _enqueue_poll(session: AsyncSession, contract: Contract, purpose: str, when: Any) -> None:
    if when is None:
        return
    await enqueue(
        session,
        Job.POLL,
        {"contract_id": contract.id, "purpose": purpose},
        dedupe_key=f"{Job.POLL}:{contract.id}:{purpose}",
        run_after=when,
    )


def _retryable(exc: AgentCallError) -> bool:
    text = str(exc).lower()
    terminal = ("didn't complete", "isn't json", "without a delivery")
    return not any(phrase in text for phrase in terminal)
