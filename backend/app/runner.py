"""Job runner entry point: `python -m app.runner` (the `runner` Compose service)."""

import asyncio
import os
import signal
import socket
import sys
from datetime import timedelta

from app.core.config import ConfigurationError, Settings, load_settings
from app.core.logging import get_logger, setup_logging
from app.db.engine import Database, DatabaseUnavailable
from app.integrations.paypal import PayPalClient, PayPalConfig
from app.jobs import HANDLERS, SCHEDULES
from app.jobs.base import JobContext
from app.jobs.runner import Runner
from app.services.paypal_audit import SqlOperationRecorder

logger = get_logger("covenant.runner")


def build_runner(settings: Settings, database: Database, paypal: PayPalClient) -> Runner:
    return Runner(
        database,
        HANDLERS,
        JobContext(settings=settings, database=database, paypal=paypal),
        name=f"{socket.gethostname()}-{os.getpid()}",
        batch_size=settings.runner_batch_size,
        poll_interval=settings.runner_poll_seconds,
        lease=timedelta(seconds=settings.runner_lease_seconds),
        schedules=SCHEDULES,
    )


async def main() -> None:
    try:
        settings = load_settings()
    except ConfigurationError as exc:
        print(f"Covenant runner cannot start.\n{exc}", file=sys.stderr)  # noqa: T201
        raise SystemExit(1) from None
    setup_logging(settings.log_level, json_output=settings.app_env != "development")

    database = Database.from_settings(settings)
    try:
        await database.ping()
    except DatabaseUnavailable as exc:
        logger.error("startup_failed", reason=str(exc))
        raise SystemExit(1) from None
    paypal = PayPalClient(
        PayPalConfig.from_settings(settings), recorder=SqlOperationRecorder(database)
    )

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    try:
        await build_runner(settings, database, paypal).run_forever(stop)
    finally:
        await paypal.aclose()
        await database.dispose()


if __name__ == "__main__":
    asyncio.run(main())
