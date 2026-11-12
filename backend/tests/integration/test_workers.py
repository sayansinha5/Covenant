import socket
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.services import worker_registry
from tests.integration.escrow_helpers import run_jobs
from tests.integration.helpers import signup_with_org

SPANISH = [
    {
        "id": "1",
        "translation": "La estola kantha índigo está cosida a mano por artesanas de Bengala.",
    },
    {
        "id": "2",
        "translation": "Cada pieza es única, ligera en primavera y cálida en las tardes.",
    },
    {
        "id": "3",
        "translation": "Es un regalo considerado que lleva la historia de las manos.",
    },
]


@pytest.fixture
def allow_lipi(monkeypatch: pytest.MonkeyPatch) -> None:
    """Only the demo hostname is stubbed. Replacing every lookup would send MySQL there."""
    real = socket.getaddrinfo

    def resolve(host: str, *args: object, **kwargs: object) -> list[object]:
        if host == "lipi":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("172.18.0.5", 0))]
        return real(host, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(socket, "getaddrinfo", resolve)


@pytest.fixture
def passing_agent(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    async def card(*args: object, **kwargs: object) -> dict[str, object]:
        return {
            "name": "Lipi",
            "description": "Translates listings.",
            "version": "0.1.0",
            "url": "http://lipi:9101",
            "protocolVersion": "1.0",
            "defaultInputModes": ["application/json"],
            "defaultOutputModes": ["application/json"],
            "skills": [{"id": "translate", "name": "Translate", "tags": ["translation"]}],
        }

    async def task(*args: object, **kwargs: object) -> list[dict[str, str]]:
        return SPANISH

    monkeypatch.setattr(worker_registry, "fetch_card", card)
    monkeypatch.setattr(worker_registry, "run_task", task)
    yield


async def test_marketplace_lists_verified_workers_only(
    client: AsyncClient, app: FastAPI, allow_lipi: None, passing_agent: None
) -> None:
    provider = await signup_with_org(
        client, "kabir@example.com", name="Kabir Studio", can_hire=False, can_provide=True
    )
    hirer = await signup_with_org(client, "riya@example.com", name="Kantha")
    refused = await client.post(
        "/api/v1/workers/agent",
        json={
            "base_url": "http://169.254.169.254",
            "price": "40.00",
            "categories": ["translation"],
        },
        headers=provider,
    )
    assert (refused.status_code, refused.json()["code"]) == (422, "AGENT_URL_REJECTED")

    human = await client.post(
        "/api/v1/workers/human",
        json={
            "display_name": "Arjun",
            "description": "Logos and motifs.",
            "price": "55.00",
            "categories": ["design"],
        },
        headers=provider,
    )
    assert human.status_code == 201, human.text
    assert human.json()["status"] == "verified"

    registered = await client.post(
        "/api/v1/workers/agent",
        json={"base_url": "http://lipi:9101", "price": "40.00", "categories": ["translation"]},
        headers=provider,
    )
    assert registered.status_code == 202, registered.text
    assert registered.json()["status"] == "pending"
    listed = (await client.get("/api/v1/workers", headers=hirer)).json()
    assert [item["display_name"] for item in listed["items"]] == ["Arjun"]
    own = (await client.get("/api/v1/workers", headers=provider)).json()
    assert own["status"] == 403

    await run_jobs(app)
    mine = (await client.get("/api/v1/workers/mine", headers=provider)).json()
    lipi = next(item for item in mine if item["kind"] == "agent")
    assert (lipi["display_name"], lipi["status"], lipi["skills"][0]["id"]) == (
        "Lipi",
        "verified",
        "translate",
    )
    progress = (
        await client.get(f"/api/v1/workers/{lipi['id']}/verification", headers=provider)
    ).json()
    assert [step["step"] for step in progress["steps"]] == [
        "agent_card",
        "skills",
        "test_job",
        "checks",
    ]
    assert "auth_token" not in lipi

    again = (await client.get("/api/v1/workers?category=translation", headers=hirer)).json()
    assert [item["display_name"] for item in again["items"]] == ["Lipi"]
    assert (await client.get("/api/v1/workers?category=design", headers=hirer)).json()["items"][0][
        "display_name"
    ] == "Arjun"
