"""Draft a contract from a worker and a request, then apply the mandate."""

from datetime import timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.spec_writer.spec import AcceptanceSpec
from app.ai.spec_writer.writer import SourceFile, SpecRequest, write_spec
from app.core.config import Settings
from app.core.errors import ConflictError, NotFoundError
from app.core.ids import uuid7
from app.db.base import utcnow
from app.domain.policy import Outcome
from app.domain.state_machine import Event, Job, State
from app.integrations.paypal import PayPalClient
from app.models import Approval, Contract, Worker
from app.services.contracts import SYSTEM, Actor, lock_contract, transition
from app.services.escrow import check_policy, lock_org
from app.services.notify import notify
from app.services.outbox import enqueue


class WorkerUnavailable(NotFoundError):
    def __init__(self) -> None:
        super().__init__("That worker isn't available to hire.", code="WORKER_NOT_FOUND")


class WorkerAmbiguous(ConflictError):
    def __init__(self, workers: list[Worker]) -> None:
        name = workers[0].display_name
        ids = ", ".join(worker.id for worker in workers)
        super().__init__(
            f"More than one worker is named {name}. Use one of these ids: {ids}.",
            code="WORKER_AMBIGUOUS",
        )


def _hireable(worker: Worker, org_id: str, *, require_categories: bool) -> bool:
    if worker.org_id == org_id or worker.status != "verified":
        return False
    return bool(worker.categories) if require_categories else True


async def resolve_worker(
    session: AsyncSession,
    *,
    org_id: str,
    ref: str,
    require_categories: bool = False,
) -> Worker:
    """A verified worker another org can hire, by id or by a unique display name."""
    needle = ref.strip()
    if not needle:
        raise WorkerUnavailable
    by_id = await session.get(Worker, needle)
    if by_id is not None:
        if _hireable(by_id, org_id, require_categories=require_categories):
            return by_id
        raise WorkerUnavailable
    rows = list(
        await session.scalars(
            select(Worker).where(
                func.lower(Worker.display_name) == needle.casefold(),
                Worker.status == "verified",
                Worker.org_id != org_id,
            )
        )
    )
    chosen = [row for row in rows if _hireable(row, org_id, require_categories=require_categories)]
    if len(chosen) == 1:
        return chosen[0]
    if len(chosen) > 1:
        raise WorkerAmbiguous(chosen)
    raise WorkerUnavailable


async def draft_contract(
    session: AsyncSession,
    settings: Settings,
    paypal: PayPalClient,
    *,
    org_id: str,
    user_actor: Actor,
    worker_id: str,
    request_text: str,
    budget: Decimal | None = None,
    source_rows: list[dict[str, Any]] | None = None,
    input_file_id: str | None = None,
    change_request: str | None = None,
    previous: AcceptanceSpec | None = None,
) -> tuple[Contract, str]:
    """Write a spec, save a draft and move it with the mandate outcome.

    Returns the contract and a card kind: proposal, approval or error."""
    await lock_org(session, org_id)
    worker = await resolve_worker(session, org_id=org_id, ref=worker_id, require_categories=True)
    if budget is not None and budget < worker.price:
        raise ConflictError(
            f"The budget is below this worker's price of {worker.price}.",
            code="BUDGET_TOO_LOW",
        )
    contract_id = uuid7()
    written = await write_spec(
        settings,
        SpecRequest(
            request_text=request_text,
            work_type=worker.categories[0],  # type: ignore[arg-type]
            worker_name=worker.display_name,
            worker_kind=worker.kind,  # type: ignore[arg-type]
            price=worker.price,
            currency=worker.currency,
            source=SourceFile(file_id=input_file_id, name="input", rows=source_rows or []),
            previous=previous,
            change_request=change_request,
        ),
        org_id=org_id,
        contract_id=contract_id,
    )
    spec = written.spec
    contract = Contract(
        id=contract_id,
        hirer_org_id=org_id,
        provider_org_id=worker.org_id,
        worker_id=worker.id,
        work_type=spec.work_type,
        title=spec.title,
        request_text=request_text,
        input_file_id=input_file_id,
        spec=spec.model_dump(mode="json"),
        source_items=source_rows,
        amount=worker.price,
        currency=worker.currency,
        state=State.DRAFT,
        deadline_at=utcnow() + timedelta(minutes=spec.deadline_minutes),
        created_by_actor=user_actor.type,
        version=1,
    )
    session.add(contract)
    await session.flush()
    decision, mandate_id = await check_policy(session, settings, paypal, contract)
    contract.mandate_id = mandate_id
    if decision.outcome is Outcome.NEEDS_APPROVAL:
        event, card = Event.MANDATE_NEEDS_APPROVAL, "approval"
    elif decision.outcome is Outcome.REJECTED:
        event, card = Event.MANDATE_REJECTED, "error"
    else:
        event, card = Event.MANDATE_OK, "proposal"
    await transition(
        session,
        contract,
        event,
        actor=user_actor,
        message=decision.reason,
        data={"code": decision.code},
    )
    if decision.outcome is Outcome.NEEDS_APPROVAL:
        approval = Approval(
            id=uuid7(),
            contract_id=contract.id,
            org_id=org_id,
            reason=decision.reason,
            expires_at=utcnow() + timedelta(hours=settings.approval_expiry_hours),
        )
        session.add(approval)
        await session.flush()
        await enqueue(
            session,
            Job.EXPIRE_APPROVAL,
            {"approval_id": approval.id},
            dedupe_key=f"{Job.EXPIRE_APPROVAL}:{approval.id}",
            run_after=approval.expires_at,
        )
        notify(
            session,
            org_id=org_id,
            kind="approval",
            title=f"Approval needed: {contract.title}",
            body=decision.reason,
            link="/approvals",
        )
    return contract, card


async def revise_contract(
    session: AsyncSession,
    settings: Settings,
    *,
    org_id: str,
    contract_id: str,
    change_request: str,
    user_actor: Actor,
) -> Contract:
    """Re-run the Spec Writer. The fingerprint is cleared until the hirer agrees again."""
    await lock_org(session, org_id)
    contract = await lock_contract(session, contract_id)
    if contract.hirer_org_id != org_id:
        raise NotFoundError("This contract doesn't exist.", code="CONTRACT_NOT_FOUND")
    if contract.state not in (State.AWAITING_AGREEMENT, State.AWAITING_APPROVAL):
        raise ConflictError(
            "This contract can't be changed now.",
            code="INVALID_TRANSITION",
        )
    worker = await session.get(Worker, contract.worker_id)
    if worker is None:
        raise WorkerUnavailable
    written = await write_spec(
        settings,
        SpecRequest(
            request_text=contract.request_text,
            work_type=contract.work_type,  # type: ignore[arg-type]
            worker_name=worker.display_name,
            worker_kind=worker.kind,  # type: ignore[arg-type]
            price=contract.amount,
            currency=contract.currency,
            previous=AcceptanceSpec.model_validate(contract.spec or {}),
            change_request=change_request,
        ),
        org_id=org_id,
        contract_id=contract.id,
    )
    spec = written.spec
    contract.spec = spec.model_dump(mode="json")
    contract.spec_hash = None
    contract.title = spec.title
    contract.deadline_at = utcnow() + timedelta(minutes=spec.deadline_minutes)
    from app.services.contracts import note

    note(session, contract, "The acceptance spec was revised.", actor=user_actor)
    return contract


async def expire_approval(session: AsyncSession, approval_id: str) -> None:
    approval = await session.get(Approval, approval_id)
    if approval is None or approval.status != "pending":
        return
    if approval.expires_at > utcnow():
        from app.jobs.base import RetryLater

        remaining = (approval.expires_at - utcnow()).total_seconds()
        raise RetryLater("The approval window is still open.", delay_seconds=max(remaining, 1))
    await lock_org(session, approval.org_id)
    contract = await lock_contract(session, approval.contract_id)
    approval.status = "expired"
    approval.decided_at = utcnow()
    if contract.state == State.AWAITING_APPROVAL:
        await transition(
            session,
            contract,
            Event.APPROVAL_EXPIRED,
            actor=SYSTEM,
            message="The approval window closed without a decision.",
        )


async def decide_approval(
    session: AsyncSession,
    *,
    org_id: str,
    approval_id: str,
    actor: Actor,
    actor_name: str,
    approve: bool,
) -> Contract:
    approval = await session.get(Approval, approval_id)
    if approval is None or approval.org_id != org_id:
        raise NotFoundError("This approval doesn't exist.", code="APPROVAL_NOT_FOUND")
    await lock_org(session, org_id)
    contract = await lock_contract(session, approval.contract_id)
    if approval.status != "pending" or contract.state != State.AWAITING_APPROVAL:
        raise ConflictError("This approval is no longer open.", code="INVALID_TRANSITION")
    approval.decided_by = actor.id
    approval.decided_at = utcnow()
    if approve:
        approval.status = "approved"
        event, message = Event.APPROVED, f"{actor_name} approved the spend."
    else:
        approval.status = "rejected"
        event, message = Event.REJECTED, f"{actor_name} rejected the spend."
    await transition(session, contract, event, actor=actor, message=message)
    return contract
