import asyncio
import json
from decimal import Decimal

import httpx
import pytest
import respx
from fastapi import FastAPI
from sqlalchemy import select, text, update
from sqlalchemy.exc import OperationalError

from app.db.engine import Database
from app.domain.settlement import Band
from app.domain.state_machine import State
from app.models import ContractEvent, Escrow, OutboxJob, Payout
from app.services import escrow
from tests.integration.escrow_helpers import (
    KABIR_PAYPAL,
    agree,
    authorization,
    contract_state,
    fund,
    ledger_rows,
    make_contract,
    make_hirer,
    mock_capture,
    mock_hold,
    mock_payout,
    only_payout,
    run_jobs,
    settle_as,
)

pytestmark = pytest.mark.usefixtures("clean_tables")


async def test_agree_holds_once_and_replays_the_same_key(
    app: FastAPI, client: httpx.AsyncClient, database: Database, paypal_mock: respx.MockRouter
) -> None:
    owner, org_id = await make_hirer(client, database)
    contract_id = await make_contract(database, org_id)
    orders = mock_hold(paypal_mock)

    missing = await client.post(f"/api/v1/contracts/{contract_id}/agree", headers=owner)
    assert (missing.status_code, missing.json()["code"]) == (400, "IDEMPOTENCY_KEY_REQUIRED")

    first = await agree(client, owner, contract_id, "agree-key-1")
    assert first.status_code == 202, first.text
    assert first.json()["contract"]["state"] == "funding"
    assert first.json()["policy"]["code"] == "WITHIN_MANDATE"

    replay = await agree(client, owner, contract_id, "agree-key-1")
    assert replay.status_code == 202
    assert replay.headers["Idempotent-Replayed"] == "true"
    assert replay.json() == first.json()

    second_key = await agree(client, owner, contract_id, "agree-key-2")
    assert (second_key.status_code, second_key.json()["code"]) == (409, "INVALID_TRANSITION")

    other_contract = await make_contract(database, org_id)
    reused = await agree(client, owner, other_contract, "agree-key-1")
    assert (reused.status_code, reused.json()["code"]) == (422, "IDEMPOTENCY_KEY_REUSED")

    await run_jobs(app)
    assert orders.call_count == 1
    sent = orders.calls.last.request
    assert sent.headers["PayPal-Request-Id"] == f"cov-{contract_id}-create_order-1"
    assert await contract_state(database, contract_id) == State.FUNDED
    assert await ledger_rows(database) == [(org_id, "held", Decimal("40.00"))]
    async with database.session() as session:
        held = (await session.scalars(select(Escrow))).one()
        dispatch = await session.scalar(
            select(OutboxJob.status).where(OutboxJob.kind == "worker.dispatch")
        )
    assert (held.status, held.paypal_authorization_id, held.amount_held) == (
        "held",
        "AUTH-1",
        Decimal("40.00"),
    )
    assert dispatch == "queued"


async def test_concurrent_agrees_cannot_overshoot_the_budget(
    client: httpx.AsyncClient, database: Database
) -> None:
    owner, org_id = await make_hirer(client, database, budget="100.00")
    first = await make_contract(database, org_id, "55.00")
    second = await make_contract(database, org_id, "55.00")
    responses = await asyncio.gather(
        agree(client, owner, first, "budget-key-1"), agree(client, owner, second, "budget-key-2")
    )
    assert sorted(r.status_code for r in responses) == [202, 422]
    [rejected] = [r for r in responses if r.status_code == 422]
    assert rejected.json()["code"] == "MANDATE_OVER_BUDGET"
    async with database.session() as session:
        assert len(list(await session.scalars(select(Escrow)))) == 1


async def test_amount_over_the_threshold_needs_approval(
    client: httpx.AsyncClient, database: Database
) -> None:
    owner, org_id = await make_hirer(client, database, threshold="40.00")
    contract_id = await make_contract(database, org_id, "55.00")
    response = await agree(client, owner, contract_id, "approval-key")
    assert (response.status_code, response.json()["code"]) == (409, "APPROVAL_REQUIRED")
    assert await contract_state(database, contract_id) == State.AWAITING_AGREEMENT


async def test_declined_hold_returns_the_contract_and_frees_the_budget(
    app: FastAPI, client: httpx.AsyncClient, database: Database, paypal_mock: respx.MockRouter
) -> None:
    owner, org_id = await make_hirer(client, database)
    contract_id = await make_contract(database, org_id)
    paypal_mock.post("/v2/checkout/orders").respond(
        422,
        json={"name": "UNPROCESSABLE_ENTITY", "debug_id": "dbg-1", "details": [{"issue": "X"}]},
    )
    assert (await agree(client, owner, contract_id, "decline-key")).status_code == 202
    await run_jobs(app)

    assert await contract_state(database, contract_id) == State.AWAITING_AGREEMENT
    assert await ledger_rows(database) == []
    async with database.session() as session:
        failed = (await session.scalars(select(Escrow))).one()
        assert failed.status == "failed"
        assert await escrow.committed_this_month(
            session, org_id, failed.reserved_at, excluding_contract_id="none"
        ) == Decimal("0.00")
        messages = set(await session.scalars(select(ContractEvent.message)))
    assert escrow.HOLD_DECLINED in messages

    # Agreeing again starts a new PayPal request series.
    orders = mock_hold(paypal_mock)
    assert (await agree(client, owner, contract_id, "decline-key-2")).status_code == 202
    await run_jobs(app)
    assert orders.calls.last.request.headers["PayPal-Request-Id"] == (
        f"cov-{contract_id}-create_order-2"
    )
    assert await contract_state(database, contract_id) == State.FUNDED


@pytest.mark.parametrize(
    ("outcome", "state"), [(None, State.FUNDED), ("cancel", State.AWAITING_AGREEMENT)]
)
async def test_approve_each_hold_waits_for_the_payer(
    outcome: str | None,
    state: State,
    app: FastAPI,
    client: httpx.AsyncClient,
    database: Database,
    paypal_mock: respx.MockRouter,
) -> None:
    owner, org_id = await make_hirer(client, database)
    contract_id = await make_contract(database, org_id)
    create = paypal_mock.post("/v2/checkout/orders").respond(
        200,
        json={
            "id": "ORDER-1",
            "status": "PAYER_ACTION_REQUIRED",
            "links": [{"rel": "payer-action", "href": "https://www.sandbox.paypal.com/x?t=1"}],
        },
    )
    authorize = paypal_mock.post("/v2/checkout/orders/ORDER-1/authorize").respond(
        201,
        json={
            "id": "ORDER-1",
            "status": "COMPLETED",
            "purchase_units": [{"payments": {"authorizations": [authorization("40.00")]}}],
        },
    )
    assert (await agree(client, owner, contract_id, "approve-each-1")).status_code == 202
    await run_jobs(app, paypal_funding_mode="approve_each")
    sent = json.loads(create.calls.last.request.content)["payment_source"]["paypal"]
    assert sent["experience_context"]["return_url"].endswith(escrow.ORDER_RETURN_PATH)
    async with database.session() as session:
        waiting = (await session.scalars(select(Escrow))).one()
    assert (waiting.status, waiting.payer_action_url) == (
        "payer_action",
        "https://www.sandbox.paypal.com/x?t=1",
    )

    params = {"token": "ORDER-1", **({"outcome": outcome} if outcome else {})}
    back = await client.get("/api/v1/paypal/orders/return", params=params)
    assert back.status_code == 303
    result = "cancelled" if outcome else "approved"
    assert back.headers["location"].endswith(f"/contracts/{contract_id}?paypal={result}")
    await run_jobs(app, paypal_funding_mode="approve_each")
    assert await contract_state(database, contract_id) == state
    assert authorize.call_count == (0 if outcome else 1)

    stale = await client.get("/api/v1/paypal/orders/return", params={"token": "ORDER-1"})
    assert stale.headers["location"].endswith("/?paypal=invalid")


async def test_full_capture_books_fee_and_pays_out(
    app: FastAPI, client: httpx.AsyncClient, database: Database, paypal_mock: respx.MockRouter
) -> None:
    funded = await fund(app, client, database, paypal_mock)
    capture = mock_capture(paypal_mock, "40.00")
    payouts = mock_payout(paypal_mock)
    await settle_as(app, database, funded.contract_id, Band.PASS)
    await run_jobs(app, platform_fee_rate=Decimal("0.05"), paypal_payouts_enabled=True)

    assert await contract_state(database, funded.contract_id) == State.SETTLED
    assert json.loads(capture.calls.last.request.content)["final_capture"] is True
    payout = await only_payout(database)
    assert (payout.gross, payout.fee, payout.net) == (
        Decimal("40.00"),
        Decimal("2.00"),
        Decimal("38.00"),
    )
    assert (payout.status, payout.paypal_batch_id, payout.receiver_email) == (
        "pending",
        "BATCH-1",
        KABIR_PAYPAL,
    )
    assert payouts.calls.last.request.headers["PayPal-Request-Id"] == payout.sender_batch_id
    provider = payout.provider_org_id
    assert sorted(await ledger_rows(database)) == sorted(
        [
            (funded.org_id, "held", Decimal("40.00")),
            (funded.org_id, "captured", Decimal("40.00")),
            (provider, "fee", Decimal("2.00")),
        ]
    )

    paypal_mock.get("/v1/payments/payouts/BATCH-1").respond(
        json={
            "batch_header": {"payout_batch_id": "BATCH-1", "batch_status": "SUCCESS"},
            "items": [{"payout_item_id": "ITEM-1", "transaction_status": "SUCCESS"}],
        }
    )
    async with database.session() as session, session.begin():
        await session.execute(
            update(OutboxJob)
            .where(OutboxJob.kind == "payout.sync")
            .values(run_after=OutboxJob.created_at)
        )
    await run_jobs(app)
    assert (await only_payout(database)).status == "success"
    assert (provider, "paid_out", Decimal("38.00")) in await ledger_rows(database)


async def test_partial_capture_releases_the_rest(
    app: FastAPI, client: httpx.AsyncClient, database: Database, paypal_mock: respx.MockRouter
) -> None:
    funded = await fund(app, client, database, paypal_mock)
    capture = mock_capture(paypal_mock, "24.00")
    mock_payout(paypal_mock)
    await settle_as(app, database, funded.contract_id, Band.PARTIAL, ratio="0.6")
    await run_jobs(app, platform_fee_rate=Decimal("0.05"), paypal_payouts_enabled=True)

    assert await contract_state(database, funded.contract_id) == State.PARTIALLY_SETTLED
    sent = json.loads(capture.calls.last.request.content)
    assert (sent["amount"]["value"], sent["final_capture"]) == ("24.00", True)
    payout = await only_payout(database)
    assert (payout.gross, payout.fee, payout.net) == (
        Decimal("24.00"),
        Decimal("1.20"),
        Decimal("22.80"),
    )
    async with database.session() as session:
        held = (await session.scalars(select(Escrow))).one()
    assert (held.amount_captured, held.amount_released) == (Decimal("24.00"), Decimal("16.00"))
    assert sorted(await ledger_rows(database)) == sorted(
        [
            (funded.org_id, "held", Decimal("40.00")),
            (funded.org_id, "captured", Decimal("24.00")),
            (funded.org_id, "released", Decimal("16.00")),
            (payout.provider_org_id, "fee", Decimal("1.20")),
        ]
    )


async def test_payout_failure_leaves_the_contract_settled(
    app: FastAPI, client: httpx.AsyncClient, database: Database, paypal_mock: respx.MockRouter
) -> None:
    funded = await fund(app, client, database, paypal_mock)
    mock_capture(paypal_mock, "40.00")
    paypal_mock.post("/v1/payments/payouts").respond(
        422,
        json={"name": "RECEIVER_UNREGISTERED", "message": "Receiver is unregistered"},
    )
    await settle_as(app, database, funded.contract_id, Band.PASS)
    await run_jobs(app, paypal_payouts_enabled=True)

    assert await contract_state(database, funded.contract_id) == State.SETTLED
    payout = await only_payout(database)
    assert (payout.status, payout.failure_reason) == ("failed", "Receiver is unregistered")


async def test_payouts_disabled_leaves_the_payout_pending(
    app: FastAPI, client: httpx.AsyncClient, database: Database, paypal_mock: respx.MockRouter
) -> None:
    funded = await fund(app, client, database, paypal_mock)
    mock_capture(paypal_mock, "40.00")
    payouts = mock_payout(paypal_mock)
    await settle_as(app, database, funded.contract_id, Band.PASS)
    await run_jobs(app, paypal_payouts_enabled=False)

    assert not payouts.called
    payout = await only_payout(database)
    assert (payout.status, payout.paypal_batch_id) == ("pending", None)


@pytest.mark.parametrize("band", [Band.FAIL, Band.MANIPULATION])
async def test_failed_work_voids_the_hold(
    band: Band,
    app: FastAPI,
    client: httpx.AsyncClient,
    database: Database,
    paypal_mock: respx.MockRouter,
) -> None:
    funded = await fund(app, client, database, paypal_mock)
    void = paypal_mock.post("/v2/payments/authorizations/AUTH-1/void").respond(
        200, json=authorization("40.00", "VOIDED")
    )
    await settle_as(app, database, funded.contract_id, band)
    await run_jobs(app)

    assert void.call_count == 1
    assert await contract_state(database, funded.contract_id) == State.REFUNDED
    assert sorted(await ledger_rows(database)) == [
        (funded.org_id, "held", Decimal("40.00")),
        (funded.org_id, "released", Decimal("40.00")),
    ]
    async with database.session() as session:
        assert (await session.scalars(select(Payout))).first() is None


async def test_cancelling_a_funded_contract_releases_the_hold(
    app: FastAPI, client: httpx.AsyncClient, database: Database, paypal_mock: respx.MockRouter
) -> None:
    funded = await fund(app, client, database, paypal_mock)
    paypal_mock.post("/v2/payments/authorizations/AUTH-1/void").respond(
        200, json=authorization("40.00", "VOIDED")
    )
    response = await client.post(
        f"/api/v1/contracts/{funded.contract_id}/cancel",
        headers={**funded.owner, "Idempotency-Key": "cancel-key-1"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["contract"]["state"] == "cancelled"
    await run_jobs(app)
    assert (funded.org_id, "released", Decimal("40.00")) in await ledger_rows(database)
    async with database.session() as session:
        assert (await session.scalars(select(Escrow.status))).one() == "voided"


async def test_ledger_is_append_only_for_the_app(
    app: FastAPI, client: httpx.AsyncClient, database: Database, paypal_mock: respx.MockRouter
) -> None:
    await fund(app, client, database, paypal_mock)
    for statement in ("UPDATE ledger_entries SET amount = 0", "DELETE FROM ledger_entries"):
        with pytest.raises(OperationalError, match="command denied"):
            async with database.session() as session, session.begin():
                await session.execute(text(statement))
