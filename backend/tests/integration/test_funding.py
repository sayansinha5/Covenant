import json
import re
from urllib.parse import parse_qs, urlparse

import httpx
import respx
from sqlalchemy import select, update

from app.db.engine import Database
from app.models import Membership, PayPalVaultSession
from tests.integration.helpers import PASSWORD, signup_with_org

MANDATE = {
    "monthly_budget": "300.00",
    "per_task_cap": "60.00",
    "approval_threshold": "40.00",
    "allowed_work_types": ["design", "translation", "catalog_data", "copywriting"],
    "password": PASSWORD,
}
APPROVE_URL = "https://www.sandbox.paypal.com/agreements/approve?approval_session_id=AS-1"


def mock_vault(paypal_mock: respx.MockRouter) -> tuple[respx.Route, respx.Route]:
    setup = paypal_mock.post("/v3/vault/setup-tokens").respond(
        200,
        json={
            "id": "5C991763VB2781612",
            "status": "PAYER_ACTION_REQUIRED",
            "links": [{"rel": "approve", "href": APPROVE_URL, "method": "GET"}],
        },
    )
    token = paypal_mock.post("/v3/vault/payment-tokens").respond(
        200,
        json={
            "id": "8kk8451t",
            "customer": {"id": "customer_4029352050"},
            "payment_source": {"paypal": {"email_address": "riya-buyer@personal.example.com"}},
        },
    )
    return setup, token


def callback_state(setup: respx.Route) -> str:
    body = json.loads(setup.calls.last.request.content)
    return_url = body["payment_source"]["paypal"]["experience_context"]["return_url"]
    return parse_qs(urlparse(return_url).query)["state"][0]


async def test_mandate_signing_versions_and_password(client: httpx.AsyncClient) -> None:
    owner = await signup_with_org(client)
    overview = await client.get("/api/v1/mandate", headers=owner)
    assert overview.status_code == 200
    assert overview.json()["active"] is None
    assert overview.json()["defaults"]["per_task_cap"] == "60.00"

    wrong = await client.post(
        "/api/v1/mandate", json={**MANDATE, "password": "not my password 1"}, headers=owner
    )
    assert wrong.status_code == 403
    assert wrong.json()["code"] == "PASSWORD_INCORRECT"

    first = await client.post("/api/v1/mandate", json=MANDATE, headers=owner)
    assert first.status_code == 201, first.text
    assert first.json()["version"] == 1
    assert first.json()["allowed_work_types"] == [
        "translation",
        "catalog_data",
        "copywriting",
        "design",
    ]
    assert first.json()["signed_by_name"] == "Maya Rao"

    second = await client.post(
        "/api/v1/mandate", json={**MANDATE, "monthly_budget": "500.00"}, headers=owner
    )
    assert second.json()["version"] == 2

    versions = (await client.get("/api/v1/mandate/versions", headers=owner)).json()
    assert [(v["version"], v["is_active"]) for v in versions] == [(2, True), (1, False)]
    assert (await client.get("/api/v1/mandate", headers=owner)).json()["active"]["version"] == 2


async def test_mandate_validation_maps_to_fields(client: httpx.AsyncClient) -> None:
    owner = await signup_with_org(client)
    response = await client.post(
        "/api/v1/mandate",
        json={**MANDATE, "per_task_cap": "400.00", "allowed_work_types": []},
        headers=owner,
    )
    assert response.status_code == 422
    fields = {e["field"] for e in response.json()["errors"]}
    assert fields == {"per_task_cap", "allowed_work_types"}

    floats = await client.post(
        "/api/v1/mandate", json={**MANDATE, "monthly_budget": 300.5}, headers=owner
    )
    assert floats.status_code == 422


async def test_only_owners_of_hiring_orgs_sign_mandates(
    client: httpx.AsyncClient, database: Database
) -> None:
    provider = await signup_with_org(client, "ravi@example.com", can_hire=False, can_provide=True)
    assert (await client.get("/api/v1/mandate", headers=provider)).json()["code"] == "HIRE_DISABLED"

    owner = await signup_with_org(client)
    async with database.session() as db, db.begin():
        await db.execute(update(Membership).values(role="admin"))
    response = await client.post("/api/v1/mandate", json=MANDATE, headers=owner)
    assert response.status_code == 403
    assert response.json()["code"] == "ROLE_FORBIDDEN"


async def test_vault_connect_flow(client: httpx.AsyncClient, paypal_mock: respx.MockRouter) -> None:
    owner = await signup_with_org(client)
    setup, token = mock_vault(paypal_mock)

    before = (await client.get("/api/v1/paypal/funding-account", headers=owner)).json()
    assert before == {
        "mode": "vault",
        "connected": False,
        "payer_email": None,
        "connected_at": None,
    }

    started = await client.post(
        "/api/v1/paypal/vault/start", json={"return_path": "/onboarding"}, headers=owner
    )
    assert started.status_code == 201, started.text
    assert started.json()["approve_url"] == APPROVE_URL
    assert setup.calls.last.request.headers["PayPal-Request-Id"].startswith("cov-vault-")
    session_id = started.json()["session_id"]

    page = await client.get("/api/v1/paypal/vault/return", params={"state": callback_state(setup)})
    assert page.status_code == 200
    assert "PayPal is connected" in page.text
    nonce = re.search(r"script-src 'nonce-([^']+)'", page.headers["content-security-policy"])
    assert nonce and f'nonce="{nonce.group(1)}"' in page.text
    assert '"status": "connected"' in page.text
    sent = json.loads(token.calls.last.request.content)
    assert sent == {"payment_source": {"token": {"id": "5C991763VB2781612", "type": "SETUP_TOKEN"}}}

    status = await client.get(f"/api/v1/paypal/vault/sessions/{session_id}", headers=owner)
    assert status.json()["status"] == "connected"
    account = (await client.get("/api/v1/paypal/funding-account", headers=owner)).json()
    assert account["connected"] is True
    assert account["payer_email"] == "riya-buyer@personal.example.com"
    assert "vault_token_id" not in account and "8kk8451t" not in json.dumps(account)

    # PayPal (or the user) loading the return URL again doesn't exchange the token twice.
    await client.get("/api/v1/paypal/vault/return", params={"state": callback_state(setup)})
    assert token.call_count == 1


async def test_vault_cancel_and_unknown_state(
    client: httpx.AsyncClient, paypal_mock: respx.MockRouter
) -> None:
    owner = await signup_with_org(client)
    setup, token = mock_vault(paypal_mock)
    started = await client.post(
        "/api/v1/paypal/vault/start", json={"return_path": "/onboarding"}, headers=owner
    )
    cancelled = await client.get(
        "/api/v1/paypal/vault/return",
        params={"state": callback_state(setup), "outcome": "cancel"},
    )
    assert "cancelled. Nothing was saved." in cancelled.text
    assert token.call_count == 0
    session = await client.get(
        f"/api/v1/paypal/vault/sessions/{started.json()['session_id']}", headers=owner
    )
    assert session.json()["status"] == "cancelled"

    unknown = await client.get("/api/v1/paypal/vault/return", params={"state": "forged"})
    assert "no longer valid" in unknown.text


async def test_vault_return_path_must_stay_in_the_app(client: httpx.AsyncClient) -> None:
    owner = await signup_with_org(client)
    for path in ("https://evil.example", "//evil.example", "/ok?x=1"):
        response = await client.post(
            "/api/v1/paypal/vault/start", json={"return_path": path}, headers=owner
        )
        assert response.status_code == 422, path


async def test_paypal_failure_marks_session_failed(
    client: httpx.AsyncClient, paypal_mock: respx.MockRouter, database: Database
) -> None:
    owner = await signup_with_org(client)
    paypal_mock.post("/v3/vault/setup-tokens").respond(
        422, json={"name": "UNPROCESSABLE_ENTITY", "message": "nope"}
    )
    response = await client.post(
        "/api/v1/paypal/vault/start", json={"return_path": "/settings"}, headers=owner
    )
    assert response.status_code == 502
    assert response.json()["code"] == "PAYPAL_ERROR"
    async with database.session() as db:
        sessions = (await db.scalars(select(PayPalVaultSession))).all()
    assert [(s.status, s.failure_reason) for s in sessions] == [
        ("failed", "PayPal couldn't start the connection.")
    ]


async def test_disconnect_deletes_the_vault_token(
    client: httpx.AsyncClient, paypal_mock: respx.MockRouter
) -> None:
    owner = await signup_with_org(client)
    setup, _ = mock_vault(paypal_mock)
    delete = paypal_mock.delete("/v3/vault/payment-tokens/8kk8451t").respond(204)
    await client.post(
        "/api/v1/paypal/vault/start", json={"return_path": "/settings"}, headers=owner
    )
    await client.get("/api/v1/paypal/vault/return", params={"state": callback_state(setup)})

    response = await client.delete("/api/v1/paypal/funding-account", headers=owner)
    assert response.status_code == 204
    assert delete.call_count == 1
    account = (await client.get("/api/v1/paypal/funding-account", headers=owner)).json()
    assert account["connected"] is False


async def test_onboarding_completes_only_when_requirements_are_met(
    client: httpx.AsyncClient, paypal_mock: respx.MockRouter
) -> None:
    owner = await signup_with_org(client)
    incomplete = await client.post("/api/v1/orgs/current/onboarding/complete", headers=owner)
    assert incomplete.status_code == 409
    assert incomplete.json()["detail"] == "To finish setup, connect PayPal and sign a mandate."

    setup, _ = mock_vault(paypal_mock)
    await client.post(
        "/api/v1/paypal/vault/start", json={"return_path": "/onboarding"}, headers=owner
    )
    await client.get("/api/v1/paypal/vault/return", params={"state": callback_state(setup)})
    await client.post("/api/v1/mandate", json=MANDATE, headers=owner)

    done = await client.post("/api/v1/orgs/current/onboarding/complete", headers=owner)
    assert done.status_code == 200
    assert done.json()["onboarded_at"] is not None
