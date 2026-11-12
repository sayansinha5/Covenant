from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI

from app.core.config import Settings
from app.db.engine import DatabaseUnavailable
from app.main import create_app
from tests.conftest import make_settings


class FakeDatabase:
    def __init__(self, healthy: bool = True) -> None:
        self.healthy = healthy
        self.disposed = False

    def describe(self) -> str:
        return "covenant_app@fake:3306/covenant"

    async def ping(self) -> None:
        if not self.healthy:
            raise DatabaseUnavailable("Cannot reach MySQL as covenant_app@fake: (1045) denied")

    async def dispose(self) -> None:
        self.disposed = True


def build_app(settings: Settings, *, healthy: bool = True) -> FastAPI:
    return create_app(settings, FakeDatabase(healthy))  # type: ignore[arg-type]


@pytest.fixture
async def client(settings: Settings) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=build_app(settings))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        yield http


async def test_health_reports_components(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "environment": "test",
        "paypal_env": "sandbox",
        "components": {
            "database": "ok",
            "paypal": "not_configured",
            "ai": "not_configured",
            "langsmith": "off",
            "channel3": "not_configured",
            "astropods": "not_configured",
            "elastic": "not_configured",
        },
    }


async def test_health_degraded_when_database_down(settings: Settings) -> None:
    transport = httpx.ASGITransport(app=build_app(settings, healthy=False))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        response = await http.get("/api/v1/health")
    assert response.status_code == 503
    assert response.json()["components"]["database"] == "error"


async def test_health_reports_configured_credentials() -> None:
    settings = make_settings(
        paypal_client_id="id",
        paypal_client_secret="secret",
        ai_provider="anthropic",
        ai_model="model",
        ai_api_key="key",
        langsmith_tracing=True,
        langsmith_api_key="ls",
        channel3_api_key="channel3-test",
        astropods_api_token="astropods-test",
        astropods_account="covenant",
    )
    transport = httpx.ASGITransport(app=build_app(settings))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        components = (await http.get("/api/v1/health")).json()["components"]
    assert components == {
        "database": "ok",
        "paypal": "configured",
        "ai": "configured",
        "langsmith": "on",
        "channel3": "configured",
        "astropods": "configured",
        "elastic": "not_configured",
    }


async def test_request_id_is_echoed_or_generated(client: httpx.AsyncClient) -> None:
    echoed = await client.get("/api/v1/health", headers={"X-Request-ID": "req-12345678"})
    assert echoed.headers["X-Request-ID"] == "req-12345678"
    generated = await client.get("/api/v1/health", headers={"X-Request-ID": "bad id\n"})
    assert generated.headers["X-Request-ID"] != "bad id\n"
    assert len(generated.headers["X-Request-ID"]) == 32


async def test_security_headers(client: httpx.AsyncClient) -> None:
    headers = (await client.get("/api/v1/health")).headers
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["Referrer-Policy"] == "no-referrer"
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["Cache-Control"] == "no-store"
    assert "default-src 'none'" in headers["Content-Security-Policy"]


async def test_unknown_route_is_problem_details(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/nope", headers={"X-Request-ID": "req-abcdefgh"})
    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["code"] == "NOT_FOUND"
    assert body["status"] == 404
    assert body["request_id"] == "req-abcdefgh"
    assert body["type"] == "urn:covenant:problem:not_found"


async def test_cors_allows_only_configured_origin(client: httpx.AsyncClient) -> None:
    preflight = {"Access-Control-Request-Method": "POST"}
    allowed = await client.options(
        "/api/v1/health", headers={**preflight, "Origin": "http://localhost:5173"}
    )
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert allowed.headers["access-control-allow-credentials"] == "true"
    denied = await client.options(
        "/api/v1/health", headers={**preflight, "Origin": "http://evil.test"}
    )
    assert "access-control-allow-origin" not in denied.headers


async def test_docs_only_in_development() -> None:
    for env, expected in (("development", 200), ("test", 404)):
        transport = httpx.ASGITransport(app=build_app(make_settings(app_env=env)))
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
            assert (await http.get("/docs")).status_code == expected


async def test_startup_fails_clearly_when_database_unreachable(settings: Settings) -> None:
    app = build_app(settings, healthy=False)
    with pytest.raises(DatabaseUnavailable, match="1045"):
        async with app.router.lifespan_context(app):
            pass
