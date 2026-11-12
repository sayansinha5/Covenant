import json
from typing import Any

import httpx
import pytest
import respx
from fastapi import FastAPI
from sqlalchemy import select, update

from app.db.engine import Database
from app.domain.settlement import Band
from app.domain.state_machine import State
from app.models import Escrow, OutboxJob, Payout, ReconciliationRun, WebhookEvent, Worker
from app.seed.admin import seed_admin
from app.services import reconcile
from tests.integration.escrow_helpers import (
    KABIR_PAYPAL,
    agree,
    authorization,
    capture_body,
    contract_state,
    fund,
    ledger_rows,
    make_contract,
    make_hirer,
    mock_capture,
    mock_payout,
    only_payout,
    run_jobs,
    settle_as,
)
from tests.integration.helpers import bearer, signup_with_org

pytestmark = pytest.mark.usefixtures("clean_tables")

TRANSMISSION = {
    "PAYPAL-AUTH-ALGO": "SHA256withRSA",
    "PAYPAL-CERT-URL": "https://api.sandbox.paypal.com/v1/notifications/certs/CERT-1",
    "PAYPAL-TRANSMISSION-ID": "tid-1",
    "PAYPAL-TRANSMISSION-SIG": "sig",
    "PAYPAL-TRANSMISSION-TIME": "2026-11-03T10:00:00Z",
}


def mock_verification(paypal_mock: respx.MockRouter, status: str = "SUCCESS") -> respx.Route:
    return paypal_mock.post("/v1/notifications/verify-webhook-signature").respond(
        200, json={"verification_status": status}
    )


def event(event_id: str, event_type: str, resource: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": event_id,
        "event_type": event_type,
        "resource_type": event_type.split(".")[1].lower(),
        "resource": resource,
        "create_time": "2026-11-03T10:00:00Z",
    }


async def deliver(client: httpx.AsyncClient, body: dict[str, Any]) -> httpx.Response:
    return await client.post(
        "/api/v1/webhooks/paypal",
        content=json.dumps(body),
        headers={**TRANSMISSION, "Content-Type": "application/json"},
    )


async def webhook_rows(database: Database) -> list[WebhookEvent]:
    async with database.session() as session:
        return list(await session.scalars(select(WebhookEvent).order_by(WebhookEvent.received_at)))


def captured_event(event_id: str = "WH-CAP-1", amount: str = "40.00") -> dict[str, Any]:
    return event(
        event_id,
        "PAYMENT.CAPTURE.COMPLETED",
        {
            **capture_body(amount),
            "final_capture": True,
            "supplementary_data": {"related_ids": {"authorization_id": "AUTH-1"}},
        },
    )


async def test_forged_webhook_is_rejected_and_logged_without_its_payload(
    client: httpx.AsyncClient, database: Database, paypal_mock: respx.MockRouter
) -> None:
    verify = mock_verification(paypal_mock, "FAILURE")
    forged = await deliver(client, captured_event("WH-FORGED"))
    assert (forged.status_code, forged.json()["code"]) == (400, "WEBHOOK_REJECTED")
    sent = json.loads(verify.calls.last.request.content)
    assert (sent["webhook_id"], sent["transmission_id"]) == ("WH-TEST", "tid-1")

    no_headers = await client.post("/api/v1/webhooks/paypal", json=captured_event("WH-BARE"))
    assert no_headers.status_code == 400
    assert verify.call_count == 1

    garbage = await client.post(
        "/api/v1/webhooks/paypal", content=b"not json", headers={"Content-Type": "text/plain"}
    )
    assert garbage.status_code == 400

    rows = await webhook_rows(database)
    assert [(r.verified, r.processed, r.paypal_event_id, r.payload) for r in rows] == [
        (False, False, None, {"claimed_event_id": "WH-FORGED"}),
        (False, False, None, {"claimed_event_id": "WH-BARE"}),
    ]
    async with database.session() as session:
        assert (await session.scalars(select(OutboxJob))).first() is None


async def test_capture_webhook_completes_a_pending_capture_once(
    app: FastAPI, client: httpx.AsyncClient, database: Database, paypal_mock: respx.MockRouter
) -> None:
    funded = await fund(app, client, database, paypal_mock)
    mock_capture(paypal_mock, "40.00", status="PENDING")
    mock_payout(paypal_mock)
    await settle_as(app, database, funded.contract_id, Band.PASS)
    await run_jobs(app, paypal_payouts_enabled=True)
    assert await contract_state(database, funded.contract_id) == State.SETTLING
    async with database.session() as session:
        assert (await session.scalars(select(Escrow.status))).one() == "capture_pending"

    mock_verification(paypal_mock)
    first = await deliver(client, captured_event())
    assert (first.status_code, first.json()) == (200, {"status": "accepted"})
    replay = await deliver(client, captured_event())
    assert (replay.status_code, replay.json()) == (200, {"status": "duplicate"})
    await run_jobs(app, paypal_payouts_enabled=True)

    assert await contract_state(database, funded.contract_id) == State.SETTLED
    [row] = await webhook_rows(database)
    assert (row.verified, row.processed, row.result, row.contract_id) == (
        True,
        True,
        "fixed",
        funded.contract_id,
    )
    assert (await only_payout(database)).paypal_batch_id == "BATCH-1"
    directions = sorted(d for _, d, _ in await ledger_rows(database))
    assert directions == ["captured", "fee", "held"]


async def test_late_and_out_of_order_webhooks_change_nothing(
    app: FastAPI, client: httpx.AsyncClient, database: Database, paypal_mock: respx.MockRouter
) -> None:
    funded = await fund(app, client, database, paypal_mock)
    mock_verification(paypal_mock)
    created = event(
        "WH-AUTH-1",
        "PAYMENT.AUTHORIZATION.CREATED",
        {**authorization("40.00"), "custom_id": funded.contract_id},
    )
    for body in (created, captured_event(), event("WH-X", "CHECKOUT.ORDER.APPROVED", {"id": "O"})):
        assert (await deliver(client, body)).status_code == 200
    await run_jobs(app)

    assert await contract_state(database, funded.contract_id) == State.FUNDED
    rows = await webhook_rows(database)
    assert {r.paypal_event_id: (r.processed, r.result) for r in rows} == {
        "WH-AUTH-1": (True, "ignored"),
        "WH-CAP-1": (True, "ignored"),
        "WH-X": (True, "ignored"),
    }
    assert len(await ledger_rows(database)) == 1


async def test_void_seen_mid_work_needs_attention(
    app: FastAPI, client: httpx.AsyncClient, database: Database, paypal_mock: respx.MockRouter
) -> None:
    funded = await fund(app, client, database, paypal_mock)
    mock_verification(paypal_mock)
    voided = event("WH-VOID-1", "PAYMENT.AUTHORIZATION.VOIDED", authorization("40.00", "VOIDED"))
    assert (await deliver(client, voided)).status_code == 200
    await run_jobs(app)

    assert await contract_state(database, funded.contract_id) == State.NEEDS_ATTENTION
    assert (funded.org_id, "released", 40) in [
        (org, d, int(amount)) for org, d, amount in await ledger_rows(database)
    ]
    [row] = await webhook_rows(database)
    assert row.result == "needs_attention"


async def test_payout_item_webhooks_track_unclaimed_then_returned(
    app: FastAPI, client: httpx.AsyncClient, database: Database, paypal_mock: respx.MockRouter
) -> None:
    funded = await fund(app, client, database, paypal_mock)
    mock_capture(paypal_mock, "40.00")
    mock_payout(paypal_mock)
    await settle_as(app, database, funded.contract_id, Band.PASS)
    await run_jobs(app, paypal_payouts_enabled=True)

    mock_verification(paypal_mock)
    item = {
        "payout_item_id": "ITEM-1",
        "payout_batch_id": "BATCH-1",
        "payout_item": {"sender_item_id": "C-1"},
        "errors": {"name": "RECEIVER_UNREGISTERED", "message": "Receiver is unregistered"},
    }
    unclaimed = {**item, "transaction_status": "UNCLAIMED"}
    returned = {**item, "transaction_status": "RETURNED"}
    await deliver(client, event("WH-P-1", "PAYMENT.PAYOUTS-ITEM.UNCLAIMED", unclaimed))
    await run_jobs(app)
    payout = await only_payout(database)
    assert (payout.status, payout.receiver_email) == ("unclaimed", KABIR_PAYPAL)

    await deliver(client, event("WH-P-2", "PAYMENT.PAYOUTS-ITEM.RETURNED", returned))
    await run_jobs(app)
    payout = await only_payout(database)
    assert (payout.status, payout.failure_reason) == ("returned", "Receiver is unregistered")
    assert await contract_state(database, funded.contract_id) == State.SETTLED


async def test_reconcile_fixes_a_hold_whose_response_was_lost(
    app: FastAPI, client: httpx.AsyncClient, database: Database, paypal_mock: respx.MockRouter
) -> None:
    owner, org_id = await make_hirer(client, database)
    contract_id = await make_contract(database, org_id)
    assert (await agree(client, owner, contract_id, "lost-key-1")).status_code == 202
    # As if PayPal created the order but the job never saw the response.
    async with database.session() as session, session.begin():
        await session.execute(update(OutboxJob).values(status="dead"))
        await session.execute(update(Escrow).values(paypal_order_id="ORDER-1"))
    paypal_mock.get("/v2/checkout/orders/ORDER-1").respond(
        json={
            "id": "ORDER-1",
            "status": "COMPLETED",
            "purchase_units": [{"payments": {"authorizations": [authorization("40.00")]}}],
        }
    )
    settings = app.state.settings
    run_id = await reconcile.run(database, settings, app.state.paypal, None)

    assert await contract_state(database, contract_id) == State.FUNDED
    async with database.session() as session:
        summary = await session.get_one(ReconciliationRun, run_id)
    assert (summary.status, summary.checked, summary.fixed, summary.needs_attention) == (
        "done",
        1,
        1,
        0,
    )
    assert summary.findings[0]["contract_id"] == contract_id
    assert summary.findings[0]["contract_number"].startswith("C-")

    paypal_mock.get("/v2/payments/authorizations/AUTH-1").respond(json=authorization("40.00"))
    again = await reconcile.run(database, settings, app.state.paypal, None)
    async with database.session() as session:
        second = await session.get_one(ReconciliationRun, again)
    assert (second.checked, second.in_sync, second.fixed) == (1, 1, 0)


async def test_reconcile_flags_what_it_cannot_fix(
    app: FastAPI, client: httpx.AsyncClient, database: Database, paypal_mock: respx.MockRouter
) -> None:
    funded = await fund(app, client, database, paypal_mock)
    paypal_mock.get("/v2/payments/authorizations/AUTH-1").respond(
        json=authorization("40.00", "CAPTURED")
    )
    run_id = await reconcile.run(database, app.state.settings, app.state.paypal, None)

    assert await contract_state(database, funded.contract_id) == State.NEEDS_ATTENTION
    async with database.session() as session:
        summary = await session.get_one(ReconciliationRun, run_id)
    assert (summary.needs_attention, summary.findings[0]["result"]) == (1, "needs_attention")
    assert "CAPTURED" in summary.findings[0]["message"]


async def test_reconcile_settles_a_capture_and_counts_paypal_errors(
    app: FastAPI, client: httpx.AsyncClient, database: Database, paypal_mock: respx.MockRouter
) -> None:
    funded = await fund(app, client, database, paypal_mock)
    mock_capture(paypal_mock, "40.00", status="PENDING")
    await settle_as(app, database, funded.contract_id, Band.PASS)
    await run_jobs(app, paypal_payouts_enabled=False)

    auth = paypal_mock.get("/v2/payments/authorizations/AUTH-1")
    auth.respond(503, json={"name": "SERVICE_UNAVAILABLE", "debug_id": "d"})
    errored = await reconcile.run(database, app.state.settings, app.state.paypal, None)
    async with database.session() as session:
        assert (await session.get_one(ReconciliationRun, errored)).errors == 1

    auth.respond(json=authorization("40.00", "CAPTURED"))
    paypal_mock.get("/v2/checkout/orders/ORDER-1").respond(
        json={
            "id": "ORDER-1",
            "status": "COMPLETED",
            "purchase_units": [{"payments": {"captures": [capture_body("40.00")]}}],
        }
    )
    await reconcile.run(database, app.state.settings, app.state.paypal, None)
    assert await contract_state(database, funded.contract_id) == State.SETTLED


async def admin_headers(
    client: httpx.AsyncClient, app: FastAPI, database: Database
) -> dict[str, str]:
    settings = app.state.settings
    async with database.session() as session, session.begin():
        await seed_admin(session, settings)
    signed_in = await client.post(
        "/api/v1/auth/login",
        json={
            "email": settings.seed_admin_email,
            "password": settings.seed_admin_password.get_secret_value(),
        },
    )
    assert signed_in.status_code == 200, signed_in.text
    return bearer(signed_in.json()["access_token"])


async def test_admin_routes_are_for_platform_admins_only(client: httpx.AsyncClient) -> None:
    owner = await signup_with_org(client)
    for path in ("/api/v1/admin/workers", "/api/v1/admin/webhook-events"):
        response = await client.get(path, headers=owner)
        assert (response.status_code, response.json()["code"]) == (403, "ADMIN_ONLY")
    assert (await client.post("/api/v1/admin/reconcile", headers=owner)).status_code == 403


async def test_admin_runs_reconciliation_and_lists_webhooks(
    app: FastAPI, client: httpx.AsyncClient, database: Database, paypal_mock: respx.MockRouter
) -> None:
    admin = await admin_headers(client, app, database)
    assert (await client.get("/api/v1/admin/reconcile/last", headers=admin)).json() is None

    queued = await client.post("/api/v1/admin/reconcile", headers=admin)
    assert (queued.status_code, queued.json()["status"]) == (202, "queued")
    again = await client.post("/api/v1/admin/reconcile", headers=admin)
    assert again.json()["id"] == queued.json()["id"]
    await run_jobs(app)
    last = (await client.get("/api/v1/admin/reconcile/last", headers=admin)).json()
    assert (last["id"], last["status"], last["trigger"], last["checked"]) == (
        queued.json()["id"],
        "done",
        "admin",
        0,
    )

    mock_verification(paypal_mock, "FAILURE")
    await deliver(client, captured_event("WH-FORGED"))
    events = (await client.get("/api/v1/admin/webhook-events", headers=admin)).json()
    assert (events["total"], events["page"], events["page_size"]) == (1, 1, 25)
    [logged] = events["items"]
    assert (logged["claimed_event_id"], logged["verified"], logged["event_type"]) == (
        "WH-FORGED",
        False,
        "PAYMENT.CAPTURE.COMPLETED",
    )


async def test_admin_suspends_and_reinstates_workers(
    app: FastAPI, client: httpx.AsyncClient, database: Database
) -> None:
    _, org_id = await make_hirer(client, database)
    await make_contract(database, org_id)
    admin = await admin_headers(client, app, database)
    async with database.session() as session, session.begin():
        worker = (await session.scalars(select(Worker))).one()
        worker.status, worker.verified_at = "verified", worker.created_at
        worker_id = worker.id

    listed = (await client.get("/api/v1/admin/workers", headers=admin)).json()
    assert [(w["id"], w["org_name"], w["status"]) for w in listed["items"]] == [
        (worker_id, "Kabir Labs", "verified")
    ]
    base = f"/api/v1/admin/workers/{worker_id}"
    short = await client.post(f"{base}/suspend", json={"reason": "x"}, headers=admin)
    assert short.status_code == 422
    suspended = await client.post(
        f"{base}/suspend", json={"reason": "Returned manipulated output"}, headers=admin
    )
    assert (suspended.json()["status"], suspended.json()["suspended_reason"]) == (
        "suspended",
        "Returned manipulated output",
    )
    twice = await client.post(f"{base}/suspend", json={"reason": "again"}, headers=admin)
    assert (twice.status_code, twice.json()["code"]) == (409, "WORKER_SUSPENDED")
    reinstated = await client.post(
        f"{base}/reinstate", json={"reason": "Appeal reviewed"}, headers=admin
    )
    assert (reinstated.json()["status"], reinstated.json()["suspended_reason"]) == (
        "verified",
        None,
    )
    missing = await client.post(
        "/api/v1/admin/workers/00000000-0000-7000-8000-000000000000/suspend",
        json={"reason": "nope nope"},
        headers=admin,
    )
    assert missing.status_code == 404
    async with database.session() as session:
        assert (await session.scalars(select(Payout))).first() is None
