from typing import Any

import httpx

PASSWORD = "correct horse battery 9"
CSRF = {"X-Requested-With": "covenant"}
ORG = {
    "name": "Aranya Crafts",
    "industry": "retail_handicrafts",
    "country": "IN",
    "can_hire": True,
    "can_provide": False,
}


async def signup(client: httpx.AsyncClient, email: str = "maya@example.com") -> dict[str, Any]:
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "full_name": "Maya Rao",
            "email": email,
            "password": PASSWORD,
            "accept_sandbox": True,
        },
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def signup_with_org(
    client: httpx.AsyncClient, email: str = "maya@example.com", **org: Any
) -> dict[str, str]:
    """Signs up and creates an organization; returns auth headers carrying the owner role."""
    session = await signup(client, email)
    created = await client.post(
        "/api/v1/orgs", json={**ORG, **org}, headers=bearer(session["access_token"])
    )
    assert created.status_code == 201, created.text
    return bearer(created.json()["access_token"])
