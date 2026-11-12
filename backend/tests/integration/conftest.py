"""Integration tests run against the `covenant_test` schema with migrations applied, using the
real credentials from `.env` (not the isolated unit-test settings)."""

from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import httpx
import pytest
import respx
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from pydantic import SecretStr
from sqlalchemy import text

from app.core.config import Settings, load_settings
from app.db.engine import Database, database_url
from app.main import create_app

BACKEND_DIR = Path(__file__).resolve().parents[2]
PAYPAL_TEST_BASE_URL = "https://api-m.sandbox.paypal.com"


@pytest.fixture(scope="session")
def migrated_test_db() -> Settings:
    # Session scope runs before the per-test environment isolation, so the real values are seen.
    settings = load_settings()
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.attributes["db"] = "test"
    command.upgrade(config, "head")
    return settings


@pytest.fixture
async def database(migrated_test_db: Settings) -> AsyncIterator[Database]:
    db = Database.from_settings(migrated_test_db, test=True)
    yield db
    await db.dispose()


@pytest.fixture
async def clean_tables(migrated_test_db: Settings) -> AsyncIterator[None]:
    yield
    # TRUNCATE needs the migrator: the app user can't empty the append-only tables.
    migrator = Database(database_url(migrated_test_db, migrator=True, test=True), pool_size=1)
    try:
        async with migrator.engine.begin() as conn:
            tables = await conn.scalars(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = DATABASE() AND table_name != 'alembic_version'"
                )
            )
            await conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
            for table in tables.all():
                await conn.execute(text(f"TRUNCATE TABLE `{table}`"))
            await conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
    finally:
        await migrator.dispose()


@pytest.fixture
def app(migrated_test_db: Settings, database: Database, clean_tables: None) -> FastAPI:
    # Fake PayPal credentials: tests mock PayPal with respx and must never reach the sandbox.
    settings = migrated_test_db.model_copy(
        update={
            "login_max_attempts": 3,
            "paypal_base_url": PAYPAL_TEST_BASE_URL,
            "paypal_client_id": "test-client",
            "paypal_client_secret": SecretStr("test-secret"),
            "paypal_webhook_id": "WH-TEST",
            "paypal_funding_mode": "vault",
        }
    )
    return create_app(settings, database)


@pytest.fixture
def paypal_mock() -> Iterator[respx.MockRouter]:
    with respx.mock(base_url=PAYPAL_TEST_BASE_URL, assert_all_called=False) as router:
        router.post("/v1/oauth2/token").respond(
            200, json={"access_token": "test-access-token", "expires_in": 32400}
        )
        yield router


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as http:
        yield http
