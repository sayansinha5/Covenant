from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.engine import Database
from app.integrations.paypal import PayPalClient


@dataclass(frozen=True, slots=True)
class JobContext:
    """Process-wide dependencies handed to every job handler."""

    settings: Settings
    database: Database
    paypal: PayPalClient


class JobFailed(Exception):
    """A failure that retrying can't fix (for example a PayPal 4xx). The job becomes
    `failed` straight away and the handler's `on_give_up` runs."""


class RetryLater(Exception):
    """Not done yet; run again after `delay_seconds` (counts as an attempt)."""

    def __init__(self, reason: str, *, delay_seconds: float) -> None:
        super().__init__(reason)
        self.delay_seconds = delay_seconds


Payload = dict[str, Any]
RunJob = Callable[[AsyncSession, JobContext, Payload], Awaitable[None]]
GiveUp = Callable[[AsyncSession, JobContext, Payload, str], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class JobHandler:
    """`run` executes in a transaction that also marks the job done, so its database writes
    commit together with the job's completion. It must be safe to run more than once: work
    outside the database (PayPal, workers) is made idempotent with deterministic request IDs.

    `on_give_up` runs once when the job is `failed` or `dead`, in its own transaction, to move
    the affected contract somewhere a person will see it."""

    run: RunJob
    on_give_up: GiveUp | None = None
