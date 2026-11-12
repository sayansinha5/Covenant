"""Builders for escrow scenarios: a hirer with a signed mandate and connected PayPal, a
contract, mocked PayPal responses, and running the outbox jobs in-process."""

from datetime import timedelta
from decimal import Decimal
from typing import Any, NamedTuple

import httpx
import respx
from fastapi import FastAPI
from sqlalchemy import select, update

from app.db.engine import Database
from app.domain.settlement import Band
from app.domain.state_machine import Event, State
from app.jobs import HANDLERS
from app.jobs.base import JobContext
from app.jobs.runner import Runner
from app.models import Contract, LedgerEntry, Organization, Payout, PayPalFundingAccount, Worker
from app.services import escrow
from app.services.contracts import SYSTEM, lock_contract
from tests.integration.helpers import PASSWORD, signup_with_org

KABIR_PAYPAL = "kabir-payouts@business.example.com"


class Funded(NamedTuple):
    owner: dict[str, str]
    org_id: str
    contract_id: str


async def make_hirer(
    client: httpx.AsyncClient,
    database: Database,
    *,
    budget: str = "300.00",
    cap: str = "60.00",
    threshold: str = "60.00",
) -> tuple[dict[str, str], str]:
    owner = await signup_with_org(client)
    signed = await client.post(
        "/api/v1/mandate",
        json={
            "monthly_budget": budget,
            "per_task_cap": cap,
            "approval_threshold": threshold,
            "allowed_work_types": ["translation"],
            "password": PASSWORD,
        },
        headers=owner,
    )
    assert signed.status_code == 201, signed.text
    async with database.session() as session, session.begin():
        org_id = (await session.scalars(select(Organization.id))).one()
        session.add(
            PayPalFundingAccount(
                org_id=org_id,
                mode="vault",
                vault_token_id="VAULT-1",
                payer_email="riya-buyer@personal.example.com",
                status="connected",
            )
        )
    return owner, org_id


async def make_contract(database: Database, hirer_org_id: str, amount: str = "40.00") -> str:
    async with database.session() as session, session.begin():
        provider = Organization(
            name="Kabir Labs",
            industry="software",
            country="IN",
            can_provide=True,
            payout_email=KABIR_PAYPAL,
        )
        session.add(provider)
        await session.flush()
        worker = Worker(
            org_id=provider.id,
            kind="agent",
            display_name="Lipi",
            base_url=f"http://lipi-{provider.id}:9101",
            categories=["translation"],
            price=Decimal(amount),
            currency="USD",
        )
        session.add(worker)
        await session.flush()
        contract = Contract(
            hirer_org_id=hirer_org_id,
            provider_org_id=provider.id,
            worker_id=worker.id,
            work_type="translation",
            title="German listings for 40 stoles",
            request_text="Translate the listings into German.",
            amount=Decimal(amount),
            currency="USD",
            state=State.AWAITING_AGREEMENT,
            created_by_actor="buyer_agent",
        )
        session.add(contract)
        await session.flush()
        return contract.id


def authorization(amount: str, status: str = "CREATED") -> dict[str, Any]:
    return {
        "id": "AUTH-1",
        "status": status,
        "amount": {"currency_code": "USD", "value": amount},
        "expiration_time": "2026-12-02T10:00:00Z",
    }


def capture_body(amount: str, status: str = "COMPLETED") -> dict[str, Any]:
    return {"id": "CAP-1", "status": status, "amount": {"currency_code": "USD", "value": amount}}


def mock_hold(paypal_mock: respx.MockRouter, amount: str = "40.00") -> respx.Route:
    return paypal_mock.post("/v2/checkout/orders").respond(
        201,
        json={
            "id": "ORDER-1",
            "status": "COMPLETED",
            "purchase_units": [{"payments": {"authorizations": [authorization(amount)]}}],
        },
    )


def mock_capture(
    paypal_mock: respx.MockRouter, amount: str, status: str = "COMPLETED"
) -> respx.Route:
    return paypal_mock.post("/v2/payments/authorizations/AUTH-1/capture").respond(
        201, json=capture_body(amount, status)
    )


def mock_payout(paypal_mock: respx.MockRouter) -> respx.Route:
    return paypal_mock.post("/v1/payments/payouts").respond(
        201, json={"batch_header": {"payout_batch_id": "BATCH-1", "batch_status": "PENDING"}}
    )


async def run_jobs(app: FastAPI, **settings: Any) -> None:
    context = JobContext(
        settings=app.state.settings.model_copy(update=settings),
        database=app.state.database,
        paypal=app.state.paypal,
    )
    runner = Runner(
        context.database,
        HANDLERS,
        context,
        name="test-runner",
        batch_size=10,
        poll_interval=0.01,
        lease=timedelta(minutes=5),
    )
    while await runner.run_once():
        pass


async def agree(
    client: httpx.AsyncClient, headers: dict[str, str], contract_id: str, key: str
) -> httpx.Response:
    return await client.post(
        f"/api/v1/contracts/{contract_id}/agree", headers={**headers, "Idempotency-Key": key}
    )


async def ledger_rows(database: Database) -> list[tuple[str, str, Decimal]]:
    async with database.session() as session:
        rows = await session.scalars(select(LedgerEntry).order_by(LedgerEntry.created_at))
        return [(r.org_id, r.direction, r.amount) for r in rows]


async def contract_state(database: Database, contract_id: str) -> str:
    async with database.session() as session:
        return (await session.get_one(Contract, contract_id)).state


async def only_payout(database: Database) -> Payout:
    async with database.session() as session:
        return (await session.scalars(select(Payout))).one()


async def fund(
    app: FastAPI,
    client: httpx.AsyncClient,
    database: Database,
    paypal_mock: respx.MockRouter,
) -> Funded:
    owner, org_id = await make_hirer(client, database)
    contract_id = await make_contract(database, org_id)
    mock_hold(paypal_mock)
    assert (await agree(client, owner, contract_id, "agree-key-1")).status_code == 202
    await run_jobs(app)
    assert await contract_state(database, contract_id) == State.FUNDED
    return Funded(owner, org_id, contract_id)


async def settle_as(
    app: FastAPI, database: Database, contract_id: str, band: Band, ratio: str = "1"
) -> None:
    async with database.session() as session, session.begin():
        await session.execute(
            update(Contract).where(Contract.id == contract_id).values(state=State.VERDICT_ISSUED)
        )
    async with database.session() as session, session.begin():
        contract = await lock_contract(session, contract_id)
        await escrow.begin_settlement(
            session,
            app.state.settings,
            contract,
            Event.SETTLE,
            band,
            pass_ratio=Decimal(ratio),
            actor=SYSTEM,
            message="Settling.",
        )
