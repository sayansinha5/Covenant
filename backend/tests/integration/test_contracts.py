from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm.exc import StaleDataError

from app.db.engine import Database
from app.domain.state_machine import Event, InvalidTransition, State
from app.models import Contract, ContractEvent, Organization, OutboxJob, Worker
from app.services.contracts import SYSTEM, Actor, ContractNotFound, lock_contract, transition

pytestmark = pytest.mark.usefixtures("clean_tables")

RIYA = Actor("user", "01a1a20c-0000-7000-8000-000000000001")


async def make_contract(
    database: Database,
    state: State = State.AWAITING_AGREEMENT,
    *,
    worker_url: str = "http://lipi:9101",
) -> str:
    async with database.session() as session, session.begin():
        hirer = Organization(name="Aranya Crafts", industry="retail", country="IN", can_hire=True)
        provider = Organization(name="Kabir Labs", industry="software", country="IN")
        session.add_all([hirer, provider])
        await session.flush()
        worker = Worker(
            org_id=provider.id,
            kind="agent",
            display_name="Lipi",
            base_url=worker_url,
            categories=["translation"],
            price=Decimal("55.00"),
            currency="USD",
        )
        session.add(worker)
        await session.flush()
        contract = Contract(
            hirer_org_id=hirer.id,
            provider_org_id=provider.id,
            worker_id=worker.id,
            work_type="translation",
            title="German listings for 40 stoles",
            request_text="Translate the listings into German.",
            amount=Decimal("55.00"),
            currency="USD",
            state=state,
            created_by_actor="buyer_agent",
        )
        session.add(contract)
        await session.flush()
        return contract.id


async def test_contracts_get_increasing_human_numbers(database: Database) -> None:
    first = await make_contract(database)
    second = await make_contract(database, worker_url="http://tally:9102")
    async with database.session() as session:
        a = await session.get_one(Contract, first)
        b = await session.get_one(Contract, second)
    assert b.number == a.number + 1
    assert (a.version, b.version) == (1, 1)


async def test_transition_writes_state_event_and_jobs_together(database: Database) -> None:
    contract_id = await make_contract(database)
    async with database.session() as session, session.begin():
        contract = await lock_contract(session, contract_id)
        applied = await transition(
            session, contract, Event.HIRER_AGREED, actor=RIYA, message="Riya agreed to $55.00."
        )
    assert applied.target is State.FUNDING

    async with database.session() as session:
        contract = await session.get_one(Contract, contract_id)
        events = list(await session.scalars(select(ContractEvent)))
        jobs = list(await session.scalars(select(OutboxJob)))
    assert (contract.state, contract.version) == ("funding", 2)
    assert [(e.event, e.from_state, e.to_state, e.actor_type, e.actor_id) for e in events] == [
        ("hirer_agreed", "awaiting_agreement", "funding", "user", RIYA.id)
    ]
    assert [(j.kind, j.payload, j.dedupe_key) for j in jobs] == [
        (
            "escrow.create_hold",
            {"contract_id": contract_id},
            f"escrow.create_hold:{contract_id}:v1",
        )
    ]


async def test_invalid_transition_changes_nothing(database: Database) -> None:
    contract_id = await make_contract(database)
    with pytest.raises(InvalidTransition):
        async with database.session() as session, session.begin():
            contract = await lock_contract(session, contract_id)
            await transition(session, contract, Event.CAPTURED_FULL, actor=SYSTEM, message="x")
    async with database.session() as session:
        contract = await session.get_one(Contract, contract_id)
        assert contract.state == "awaiting_agreement"
        assert list(await session.scalars(select(ContractEvent))) == []


async def test_retrying_a_hold_after_failure_enqueues_a_new_job(database: Database) -> None:
    contract_id = await make_contract(database)
    for event in (Event.HIRER_AGREED, Event.HOLD_FAILED, Event.HIRER_AGREED):
        async with database.session() as session, session.begin():
            contract = await lock_contract(session, contract_id)
            await transition(session, contract, event, actor=SYSTEM, message=str(event))
    async with database.session() as session:
        keys = sorted(await session.scalars(select(OutboxJob.dedupe_key)))
    assert keys == [
        f"escrow.create_hold:{contract_id}:v1",
        f"escrow.create_hold:{contract_id}:v3",
    ]


async def test_stale_write_is_rejected_by_the_version_check(database: Database) -> None:
    contract_id = await make_contract(database)
    async with database.session() as stale_session:
        stale = await stale_session.get_one(Contract, contract_id)
        async with database.session() as session, session.begin():
            contract = await lock_contract(session, contract_id)
            await transition(session, contract, Event.HIRER_AGREED, actor=SYSTEM, message="x")
        stale.title = "edited from an old copy"
        with pytest.raises(StaleDataError):
            await stale_session.commit()


async def test_lock_contract_404s_for_unknown_ids(database: Database) -> None:
    async with database.session() as session:
        with pytest.raises(ContractNotFound):
            await lock_contract(session, "00000000-0000-7000-8000-000000000000")
