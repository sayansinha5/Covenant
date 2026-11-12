"""Alembic environment. Runs as the migrator user (DDL rights), then re-applies the app user's
table grants so every table is DML-only for the app and append-only tables stay INSERT/SELECT.

Target the test schema with: alembic -x db=test upgrade head
"""

import asyncio
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app import models  # noqa: F401  (registers every table on Base.metadata)
from app.core.config import ConfigurationError, Settings, load_settings
from app.db.base import Base
from app.db.engine import database_url

APPEND_ONLY_TABLES = frozenset({"ledger_entries"})

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _settings() -> Settings:
    try:
        return load_settings()
    except ConfigurationError as exc:
        sys.exit(f"Migrations cannot run.\n{exc}")


def _use_test_db() -> bool:
    # `-x db=test` from the CLI, or config.attributes["db"] when called from the test suite.
    target = config.attributes.get("db") or context.get_x_argument(as_dictionary=True).get("db")
    return target == "test"


def _sync_app_grants(connection: Connection, settings: Settings, schema: str) -> None:
    user = settings.db_user
    tables = connection.execute(
        text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = :schema AND table_type = 'BASE TABLE' "
            "AND table_name <> 'alembic_version'"
        ),
        {"schema": schema},
    ).scalars()
    # Identifiers can't be bound parameters; schema, table and user names come from our own
    # settings and information_schema, never from requests.
    for table in tables:
        target = f"`{schema}`.`{table}`"
        if table in APPEND_ONLY_TABLES:
            revoke = f"REVOKE IF EXISTS UPDATE, DELETE ON {target} FROM '{user}'@'%'"
            connection.execute(text(revoke))
            connection.execute(text(f"GRANT INSERT ON {target} TO '{user}'@'%'"))
        else:
            connection.execute(text(f"GRANT INSERT, UPDATE, DELETE ON {target} TO '{user}'@'%'"))


def _run_sync(connection: Connection, settings: Settings, schema: str) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()
    _sync_app_grants(connection, settings, schema)


async def run_migrations_online() -> None:
    settings = _settings()
    test = _use_test_db()
    url = database_url(settings, migrator=True, test=test)
    engine = create_async_engine(url, poolclass=NullPool)
    async with engine.connect() as connection:
        await connection.run_sync(_run_sync, settings, url.database or "")
        await connection.commit()
    await engine.dispose()


if context.is_offline_mode():
    sys.exit("Offline SQL generation is not supported; run migrations against MySQL.")

asyncio.run(run_migrations_online())
