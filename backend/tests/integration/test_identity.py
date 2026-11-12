import httpx
from fastapi import FastAPI
from sqlalchemy import update

from app.core.security import TokenIssuer
from app.db.engine import Database
from app.models import Membership
from tests.integration.helpers import CSRF, ORG, PASSWORD, bearer, signup


async def refresh_with(client: httpx.AsyncClient, token: str) -> httpx.Response:
    client.cookies.clear()
    return await client.post(
        "/api/v1/auth/refresh", headers={**CSRF, "Cookie": f"covenant_refresh={token}"}
    )


async def test_signup_sets_refresh_cookie_and_returns_session(client: httpx.AsyncClient) -> None:
    body = await signup(client, "Maya@Example.com ")
    assert body["token_type"] == "bearer"
    assert body["user"]["email"] == "maya@example.com"
    assert body["user"]["membership"] is None

    cookie = next(c for c in client.cookies.jar if c.name == "covenant_refresh")
    assert cookie.path == "/api/v1/auth"
    assert cookie.has_nonstandard_attr("HttpOnly")

    me = await client.get("/api/v1/auth/me", headers=bearer(body["access_token"]))
    assert me.status_code == 200
    assert me.json()["full_name"] == "Maya Rao"


async def test_signup_rejects_duplicate_email_and_weak_password(client: httpx.AsyncClient) -> None:
    await signup(client)
    duplicate = await client.post(
        "/api/v1/auth/signup",
        json={
            "full_name": "Maya",
            "email": "MAYA@example.com",
            "password": PASSWORD,
            "accept_sandbox": True,
        },
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "EMAIL_TAKEN"

    weak = await client.post(
        "/api/v1/auth/signup",
        json={
            "full_name": "Ravi",
            "email": "ravi@example.com",
            "password": "short",
            "accept_sandbox": True,
        },
    )
    assert weak.status_code == 422


async def test_login_wrong_password_is_generic(client: httpx.AsyncClient) -> None:
    await signup(client)
    for email in ("maya@example.com", "nobody@example.com"):
        response = await client.post(
            "/api/v1/auth/login", json={"email": email, "password": "wrong password!!"}
        )
        assert response.status_code == 401
        assert response.json()["detail"] == "Email or password is incorrect."


async def test_login_locks_after_repeated_failures(client: httpx.AsyncClient) -> None:
    await signup(client)
    wrong = {"email": "maya@example.com", "password": "wrong password!!"}
    assert (await client.post("/api/v1/auth/login", json=wrong)).status_code == 401
    assert (await client.post("/api/v1/auth/login", json=wrong)).status_code == 401
    third = await client.post("/api/v1/auth/login", json=wrong)
    assert third.status_code == 429
    assert third.json()["code"] == "ACCOUNT_LOCKED"

    # Even the right password is refused while locked.
    right = await client.post(
        "/api/v1/auth/login", json={"email": "maya@example.com", "password": PASSWORD}
    )
    assert right.status_code == 429


async def test_refresh_rotates_and_detects_reuse(client: httpx.AsyncClient) -> None:
    await signup(client)
    first_token = client.cookies.get("covenant_refresh", path="/api/v1/auth")
    assert first_token

    rotated = await client.post("/api/v1/auth/refresh", headers=CSRF)
    assert rotated.status_code == 200
    second_token = client.cookies.get("covenant_refresh", path="/api/v1/auth")
    assert second_token and second_token != first_token

    # Replaying the old token revokes the whole family, including the new one.
    assert (await refresh_with(client, first_token)).status_code == 401
    assert (await refresh_with(client, second_token)).status_code == 401


async def test_refresh_requires_csrf_header(client: httpx.AsyncClient) -> None:
    await signup(client)
    response = await client.post("/api/v1/auth/refresh")
    assert response.status_code == 403
    assert response.json()["code"] == "CSRF_HEADER_REQUIRED"


async def test_logout_revokes_refresh_token(client: httpx.AsyncClient) -> None:
    await signup(client)
    token = client.cookies.get("covenant_refresh", path="/api/v1/auth")
    assert (await client.post("/api/v1/auth/logout", headers=CSRF)).status_code == 204

    assert token
    assert (await refresh_with(client, token)).status_code == 401


async def test_protected_routes_need_a_valid_token(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/v1/auth/me")).status_code == 401
    bad = await client.get("/api/v1/auth/me", headers=bearer("not-a-jwt"))
    assert bad.status_code == 401
    assert bad.json()["code"] == "NOT_AUTHENTICATED"


async def test_create_organization_makes_owner_and_reissues_token(
    client: httpx.AsyncClient,
) -> None:
    session = await signup(client)
    no_org = await client.get("/api/v1/orgs/current", headers=bearer(session["access_token"]))
    assert no_org.status_code == 403
    assert no_org.json()["code"] == "ORGANIZATION_REQUIRED"

    created = await client.post("/api/v1/orgs", json=ORG, headers=bearer(session["access_token"]))
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["organization"]["assistant_name"] == "Mira"
    token = body["access_token"]

    current = await client.get("/api/v1/orgs/current", headers=bearer(token))
    assert current.json()["name"] == "Aranya Crafts"
    me = await client.get("/api/v1/auth/me", headers=bearer(token))
    assert me.json()["membership"]["role"] == "owner"

    again = await client.post("/api/v1/orgs", json=ORG, headers=bearer(token))
    assert again.status_code == 409


async def test_update_organization_checks_role_and_capabilities(
    client: httpx.AsyncClient, database: Database
) -> None:
    session = await signup(client)
    created = await client.post("/api/v1/orgs", json=ORG, headers=bearer(session["access_token"]))
    token = created.json()["access_token"]

    renamed = await client.patch(
        "/api/v1/orgs/current", json={"assistant_name": "Asha"}, headers=bearer(token)
    )
    assert renamed.status_code == 200
    assert renamed.json()["assistant_name"] == "Asha"

    neither = await client.patch(
        "/api/v1/orgs/current", json={"can_hire": False}, headers=bearer(token)
    )
    assert neither.status_code == 422
    assert neither.json()["code"] == "CAPABILITY_REQUIRED"

    # The role is read from the database on every request, not trusted from the token.
    async with database.session() as db, db.begin():
        await db.execute(update(Membership).values(role="member"))
    forbidden = await client.patch(
        "/api/v1/orgs/current", json={"name": "Other"}, headers=bearer(token)
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "ROLE_FORBIDDEN"


async def test_organizations_are_isolated(client: httpx.AsyncClient) -> None:
    maya = await signup(client, "maya@example.com")
    maya_org = await client.post("/api/v1/orgs", json=ORG, headers=bearer(maya["access_token"]))
    ravi = await signup(client, "ravi@example.com")
    ravi_org = await client.post(
        "/api/v1/orgs",
        json={**ORG, "name": "Ravi Studio", "can_hire": False, "can_provide": True},
        headers=bearer(ravi["access_token"]),
    )

    maya_view = await client.get(
        "/api/v1/orgs/current", headers=bearer(maya_org.json()["access_token"])
    )
    ravi_view = await client.get(
        "/api/v1/orgs/current", headers=bearer(ravi_org.json()["access_token"])
    )
    assert maya_view.json()["name"] == "Aranya Crafts"
    assert ravi_view.json()["name"] == "Ravi Studio"
    assert ravi_view.json()["assistant_name"] is None


async def test_token_claiming_another_org_is_refused(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    maya = await signup(client, "maya@example.com")
    await client.post("/api/v1/orgs", json=ORG, headers=bearer(maya["access_token"]))
    ravi = await signup(client, "ravi@example.com")
    ravi_org = await client.post(
        "/api/v1/orgs", json={**ORG, "name": "Ravi Studio"}, headers=bearer(ravi["access_token"])
    )

    issuer: TokenIssuer = app.state.token_issuer
    forged, _ = issuer.issue(
        user_id=maya["user"]["id"], org_id=ravi_org.json()["organization"]["id"], role="owner"
    )
    response = await client.get("/api/v1/orgs/current", headers=bearer(forged))
    assert response.status_code == 401


async def test_oversized_body_is_rejected(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/login",
        content=b"{" + b" " * (2 * 1024 * 1024 + 1) + b"}",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 413
    assert response.json()["code"] == "PAYLOAD_TOO_LARGE"
