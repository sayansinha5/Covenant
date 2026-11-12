"""The outbox runner: claims due jobs with `SELECT … FOR UPDATE SKIP LOCKED`, so any number of
runner processes can poll the same table without two of them taking the same job."""

import asyncio
import contextlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.base import utcnow
from app.db.engine import Database
from app.jobs.base import JobContext, JobFailed, JobHandler, RetryLater
from app.models import OutboxJob
from app.services.outbox import enqueue

logger = get_logger("covenant.runner")

MAX_ERROR_CHARS = 2000


class LeaseLost(Exception):
    """Another runner reclaimed the job after our lease ran out; our result is discarded."""


@dataclass(frozen=True, slots=True)
class ClaimedJob:
    id: str
    kind: str
    payload: dict[str, Any]
    attempts: int
    max_attempts: int


def backoff(attempts: int) -> timedelta:
    """2 s, 4 s, 8 s, 16 s, 32 s after the 1st…5th failed attempt."""
    return timedelta(seconds=2**attempts)


def _describe(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"[:MAX_ERROR_CHARS]


class Runner:
    def __init__(
        self,
        database: Database,
        handlers: Mapping[str, JobHandler],
        context: JobContext,
        *,
        name: str,
        batch_size: int,
        poll_interval: float,
        lease: timedelta,
        schedules: Mapping[str, timedelta] | None = None,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self.database = database
        self.handlers = handlers
        self.context = context
        self.name = name
        self.batch_size = batch_size
        self.poll_interval = poll_interval
        self.lease = lease
        self.schedules = schedules or {}
        self.clock = clock
        self._scheduled_windows: dict[str, datetime] = {}

    async def run_forever(self, stop: asyncio.Event) -> None:
        logger.info("runner_started", runner=self.name, handlers=sorted(self.handlers))
        while not stop.is_set():
            try:
                await self.enqueue_scheduled()
                ran = await self.run_once()
            except Exception:
                # A database hiccup must not kill the loop; the next poll tries again.
                logger.exception("runner_poll_failed", runner=self.name)
                ran = 0
            if ran == 0:
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), timeout=self.poll_interval)
        logger.info("runner_stopped", runner=self.name)

    async def enqueue_scheduled(self) -> None:
        """Enqueue each scheduled kind once per interval window. Every runner does this; the
        window's dedupe key makes the extra copies no-ops."""
        now = self.clock()
        for kind, interval in self.schedules.items():
            midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
            window = now - (now - midnight) % interval
            if self._scheduled_windows.get(kind) == window:
                continue
            async with self.database.session() as session, session.begin():
                await enqueue(
                    session, kind, {}, dedupe_key=f"{kind}@{window.isoformat()}", run_after=window
                )
            self._scheduled_windows[kind] = window

    async def run_once(self) -> int:
        """Claim up to `batch_size` due jobs and run them one by one. Returns how many ran."""
        jobs = await self._claim()
        for job in jobs:
            await self._execute(job)
        return len(jobs)

    async def _claim(self) -> list[ClaimedJob]:
        if not self.handlers:
            return []
        now = self.clock()
        async with self.database.session() as session, session.begin():
            due = await session.scalars(
                select(OutboxJob)
                .where(
                    # Kinds this runner can't handle yet wait in the queue for one that can.
                    OutboxJob.kind.in_(self.handlers),
                    OutboxJob.run_after <= now,
                    or_(
                        OutboxJob.status == "queued",
                        # A runner that died mid-job leaves it running; reclaim after the lease.
                        and_(OutboxJob.status == "running", OutboxJob.locked_until < now),
                    ),
                )
                .order_by(OutboxJob.run_after)
                .limit(self.batch_size)
                .with_for_update(skip_locked=True)
            )
            claimed = []
            for job in due:
                job.status = "running"
                job.attempts += 1
                job.locked_by = self.name
                job.locked_until = now + self.lease
                claimed.append(
                    ClaimedJob(job.id, job.kind, dict(job.payload), job.attempts, job.max_attempts)
                )
            return claimed

    async def _execute(self, job: ClaimedJob) -> None:
        log = logger.bind(job_id=job.id, kind=job.kind, attempt=job.attempts, runner=self.name)
        handler = self.handlers[job.kind]
        try:
            async with self.database.session() as session, session.begin():
                await handler.run(session, self.context, job.payload)
                await self._finish(session, job, status="done", last_error=None)
        except LeaseLost:
            log.warning("job_lease_lost")
        except JobFailed as exc:
            await self._give_up(job, handler, "failed", _describe(exc))
            log.warning("job_failed", error=_describe(exc))
        except Exception as exc:
            error = _describe(exc)
            if job.attempts >= job.max_attempts:
                await self._give_up(job, handler, "dead", error)
                log.error("job_dead", error=error)
                return
            delay = (
                timedelta(seconds=exc.delay_seconds)
                if isinstance(exc, RetryLater)
                else backoff(job.attempts)
            )
            await self._retry(job, error, delay)
            log.info("job_retry_scheduled", error=error, delay_seconds=delay.total_seconds())
        else:
            log.info("job_done")

    async def _finish(
        self,
        session: AsyncSession,
        job: ClaimedJob,
        *,
        status: str,
        last_error: str | None,
        run_after: datetime | None = None,
    ) -> None:
        values: dict[str, Any] = {
            "status": status,
            "last_error": last_error,
            "locked_by": None,
            "locked_until": None,
            "updated_at": self.clock(),
        }
        if run_after is not None:
            values["run_after"] = run_after
        result = await session.execute(
            update(OutboxJob)
            .where(
                OutboxJob.id == job.id,
                OutboxJob.locked_by == self.name,
                OutboxJob.attempts == job.attempts,
            )
            .values(**values)
        )
        if result.rowcount != 1:  # type: ignore[attr-defined]
            raise LeaseLost

    async def _retry(self, job: ClaimedJob, error: str, delay: timedelta) -> None:
        async with self.database.session() as session, session.begin():
            with contextlib.suppress(LeaseLost):
                await self._finish(
                    session, job, status="queued", last_error=error, run_after=self.clock() + delay
                )

    async def _give_up(self, job: ClaimedJob, handler: JobHandler, status: str, error: str) -> None:
        try:
            async with self.database.session() as session, session.begin():
                await self._finish(session, job, status=status, last_error=error)
                if handler.on_give_up is not None:
                    await handler.on_give_up(session, self.context, job.payload, error)
        except LeaseLost:
            return
        except Exception as exc:
            # The give-up hook itself failed: still record the job's end state.
            logger.exception("job_give_up_hook_failed", job_id=job.id, kind=job.kind)
            async with self.database.session() as session, session.begin():
                with contextlib.suppress(LeaseLost):
                    await self._finish(
                        session, job, status=status, last_error=f"{error}\n{_describe(exc)}"
                    )
