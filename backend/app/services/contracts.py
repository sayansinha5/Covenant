from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.domain import state_machine
from app.domain.state_machine import Event, State, Transition
from app.models import Contract, ContractEvent
from app.services.outbox import enqueue


class ContractNotFound(NotFoundError):
    def __init__(self) -> None:
        super().__init__("This contract doesn't exist.", code="CONTRACT_NOT_FOUND")


@dataclass(frozen=True, slots=True)
class Actor:
    """Who caused a change, as recorded on the timeline and in the ledger."""

    type: str  # user | buyer_agent | worker | paypal | system | api_key
    id: str | None = None


SYSTEM = Actor("system")


async def lock_contract(session: AsyncSession, contract_id: str) -> Contract:
    """Load a contract with `SELECT … FOR UPDATE`; hold the lock until the caller commits."""
    contract = await session.scalar(
        select(Contract)
        .where(Contract.id == contract_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if contract is None:
        raise ContractNotFound
    return contract


async def transition(
    session: AsyncSession,
    contract: Contract,
    event: Event,
    *,
    actor: Actor,
    message: str,
    data: dict[str, Any] | None = None,
    target: State | None = None,
) -> Transition:
    """Apply `event` to a contract locked with `lock_contract`: move its state, append the
    timeline event and enqueue the transition's jobs, all in the caller's transaction.

    Ledger entries and notifications listed on the returned transition are the caller's to
    write, because their amounts and audiences depend on context only the caller has."""
    applied = state_machine.apply(State(contract.state), event, target=target)
    # The version before this UPDATE is unique per transition, so a job is enqueued once even
    # if the same transition is retried after a lost response.
    version = contract.version
    contract.state = applied.target
    session.add(
        ContractEvent(
            contract_id=contract.id,
            event=event,
            from_state=applied.source,
            to_state=applied.target,
            actor_type=actor.type,
            actor_id=actor.id,
            message=message,
            data=data,
        )
    )
    for job in applied.jobs:
        await enqueue(
            session,
            job,
            {"contract_id": contract.id},
            dedupe_key=f"{job}:{contract.id}:v{version}",
        )
    await session.flush()
    return applied


def note(
    session: AsyncSession,
    contract: Contract,
    message: str,
    *,
    actor: Actor,
    data: dict[str, Any] | None = None,
) -> None:
    """Add a timeline entry that doesn't change state (a renewed hold, a payout update)."""
    session.add(
        ContractEvent(
            contract_id=contract.id,
            event="note",
            from_state=contract.state,
            to_state=contract.state,
            actor_type=actor.type,
            actor_id=actor.id,
            message=message,
            data=data,
        )
    )
