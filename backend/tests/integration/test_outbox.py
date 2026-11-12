import asyncio
from collections import Counter
from collections.abc import AsyncIterator
from datetime import datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.base import utcnow
from app.db.engine import Database
from app.integrations.paypal import PayPalClient, PayPalConfig
from app.jobs.base import JobContext, JobFailed, JobHandler, Payload, RetryLater
from app.jobs.runner import Runner, backoff
from app.models import Organization, OutboxJob
from app.services.outbox import enqueue

pytestmark = pytest.mark.usefixtures("clean_tables")


@pytest.fixture
async def context(migrated_test_db: Settings, database: Database) -> AsyncIterator[JobContext]:
    paypal = PayPalClient(PayPalConfig.from_settings(migrated_test_db))
    yield JobContext(settings=migrated_test_db, database=database, paypal=paypal)
    await paypal.aclose()


class Clock:
    def __init__(self) -> None:
        self.now = utcnow()

    def __call__(self) -> datetime:
        return self.now

    def advance(self, delta: timedelta) -> None:
        self.now += delta


def make_runner(
    context: JobContext,
    handlers: dict[str, JobHandler],
    *,
    name: str = "runner-a",
    clock: Clock | None = None,
    lease: timedelta = timedelta(minutes=5),
) -> Runner:
    return Runner(
        context.database,
        handlers,
        context,
        name=name,
        batch_size=5,
        poll_interval=0.01,
        lease=lease,
        clock=clock or utcnow,
    )


async def jobs_by_key(database: Database) -> dict[str, OutboxJob]:
    async with database.session() as session:
        return {job.dedupe_key: job for job in await session.scalars(select(OutboxJob))}


async def add_job(database: Database, key: str, kind: str = "test.count", **kwargs: Any) -> None:
    async with database.session() as session, session.begin():
        await enqueue(session, kind, {"key": key}, dedupe_key=key, **kwargs)


async def test_job_is_only_visible_if_its_transaction_commits(
    database: Database, context: JobContext
) -> None:
    with pytest.raises(RuntimeError):
        async with database.session() as session, session.begin():
            await enqueue(session, "test.count", {}, dedupe_key="rolled-back")
            raise RuntimeError("the state change failed")
    await add_job(database, "committed")
    assert set(await jobs_by_key(database)) == {"committed"}


async def test_enqueue_is_deduplicated(database: Database) -> None:
    await add_job(database, "same")
    await add_job(database, "same")
    jobs = await jobs_by_key(database)
    assert len(jobs) == 1


async def test_two_runners_run_each_job_exactly_once(
    database: Database, context: JobContext
) -> None:
    runs: Counter[str] = Counter()
    all_ran = asyncio.Event()

    async def count(_: AsyncSession, __: JobContext, payload: Payload) -> None:
        runs[payload["key"]] += 1
        await asyncio.sleep(0.01)
        if runs.total() >= 20:
            all_ran.set()

    # A job enqueued together with a business write, as every service does.
    async with database.session() as session, session.begin():
        session.add(Organization(name="Aranya Crafts", industry="retail", country="IN"))
        for n in range(20):
            await enqueue(session, "test.count", {"key": f"job-{n}"}, dedupe_key=f"job-{n}")

    handlers = {"test.count": JobHandler(run=count)}
    stop = asyncio.Event()
    runners = [make_runner(context, handlers, name=f"runner-{n}") for n in "ab"]
    tasks = [asyncio.create_task(r.run_forever(stop)) for r in runners]
    await asyncio.wait_for(all_ran.wait(), timeout=20)
    await asyncio.sleep(0.2)  # give a duplicate run the chance to show up
    stop.set()
    await asyncio.gather(*tasks)

    assert runs == Counter({f"job-{n}": 1 for n in range(20)})
    jobs = await jobs_by_key(database)
    assert {job.status for job in jobs.values()} == {"done"}
    assert {job.attempts for job in jobs.values()} == {1}


async def test_handler_writes_commit_with_the_job(database: Database, context: JobContext) -> None:
    async def write(session: AsyncSession, _: JobContext, __: Payload) -> None:
        session.add(Organization(name="Written by job", industry="retail", country="IN"))

    async def write_then_fail(session: AsyncSession, _: JobContext, __: Payload) -> None:
        session.add(Organization(name="Rolled back", industry="retail", country="IN"))
        raise JobFailed("PayPal said no")

    await add_job(database, "ok", kind="test.write")
    await add_job(database, "bad", kind="test.fail")
    runner = make_runner(
        context,
        {"test.write": JobHandler(run=write), "test.fail": JobHandler(run=write_then_fail)},
    )
    assert await runner.run_once() == 2

    async with database.session() as session:
        names = set(await session.scalars(select(Organization.name)))
    assert names == {"Written by job"}
    jobs = await jobs_by_key(database)
    assert jobs["ok"].status == "done"
    assert jobs["bad"].status == "failed"
    assert jobs["bad"].last_error == "JobFailed: PayPal said no"


async def test_retries_back_off_then_dead_letter(database: Database, context: JobContext) -> None:
    gave_up: list[tuple[Payload, str]] = []

    async def flaky(_: AsyncSession, __: JobContext, ___: Payload) -> None:
        raise TimeoutError("PayPal timed out")

    async def give_up(_: AsyncSession, __: JobContext, payload: Payload, error: str) -> None:
        gave_up.append((payload, error))

    await add_job(database, "flaky", kind="test.flaky", max_attempts=6)
    clock = Clock()
    runner = make_runner(
        context, {"test.flaky": JobHandler(run=flaky, on_give_up=give_up)}, clock=clock
    )

    delays = []
    for attempt in range(1, 6):
        assert await runner.run_once() == 1
        job = (await jobs_by_key(database))["flaky"]
        assert (job.status, job.attempts) == ("queued", attempt)
        delays.append(job.run_after - clock.now)
        assert await runner.run_once() == 0, "not due before its backoff"
        clock.advance(job.run_after - clock.now)

    assert delays == [timedelta(seconds=s) for s in (2, 4, 8, 16, 32)]
    assert gave_up == []
    assert await runner.run_once() == 1
    job = (await jobs_by_key(database))["flaky"]
    assert (job.status, job.attempts) == ("dead", 6)
    assert gave_up == [({"key": "flaky"}, "TimeoutError: PayPal timed out")]
    clock.advance(timedelta(hours=1))
    assert await runner.run_once() == 0


async def test_retry_later_uses_the_requested_delay(
    database: Database, context: JobContext
) -> None:
    async def not_yet(_: AsyncSession, __: JobContext, ___: Payload) -> None:
        raise RetryLater("payout still pending", delay_seconds=30)

    await add_job(database, "poll", kind="test.poll")
    clock = Clock()
    await make_runner(context, {"test.poll": JobHandler(run=not_yet)}, clock=clock).run_once()
    job = (await jobs_by_key(database))["poll"]
    assert job.status == "queued"
    assert job.run_after - clock.now == timedelta(seconds=30)
    assert job.last_error == "RetryLater: payout still pending"


async def test_runner_leaves_kinds_it_has_no_handler_for(
    database: Database, context: JobContext
) -> None:
    async def noop(_: AsyncSession, __: JobContext, ___: Payload) -> None:
        return None

    await add_job(database, "mystery", kind="test.unregistered")
    await add_job(database, "known")
    assert await make_runner(context, {}).run_once() == 0
    assert await make_runner(context, {"test.count": JobHandler(run=noop)}).run_once() == 1
    jobs = await jobs_by_key(database)
    assert (jobs["mystery"].status, jobs["mystery"].attempts) == ("queued", 0)
    assert jobs["known"].status == "done"


async def test_scheduled_kinds_are_enqueued_once_per_window(
    database: Database, context: JobContext
) -> None:
    clock = Clock()
    clock.now = clock.now.replace(hour=10, minute=1)
    runners = [
        Runner(
            database,
            {},
            context,
            name=name,
            batch_size=5,
            poll_interval=0.01,
            lease=timedelta(minutes=5),
            schedules={"test.scan": timedelta(minutes=30)},
            clock=clock,
        )
        for name in ("runner-a", "runner-b")
    ]
    for runner in runners:
        await runner.enqueue_scheduled()
    clock.advance(timedelta(minutes=10))
    await runners[0].enqueue_scheduled()
    clock.advance(timedelta(minutes=20))
    await runners[1].enqueue_scheduled()
    jobs = await jobs_by_key(database)
    day = clock.now.date().isoformat()
    assert sorted(jobs) == [f"test.scan@{day}T10:00:00", f"test.scan@{day}T10:30:00"]


async def test_give_up_hook_failure_still_records_the_end_state(
    database: Database, context: JobContext
) -> None:
    async def fail(_: AsyncSession, __: JobContext, ___: Payload) -> None:
        raise JobFailed("declined")

    async def broken_hook(_: AsyncSession, __: JobContext, ___: Payload, ____: str) -> None:
        raise RuntimeError("hook bug")

    await add_job(database, "hook", kind="test.fail")
    handlers = {"test.fail": JobHandler(run=fail, on_give_up=broken_hook)}
    await make_runner(context, handlers).run_once()
    job = (await jobs_by_key(database))["hook"]
    assert job.status == "failed"
    assert job.last_error == "JobFailed: declined\nRuntimeError: hook bug"


async def test_job_of_a_crashed_runner_is_reclaimed_after_its_lease(
    database: Database, context: JobContext
) -> None:
    runs: list[str] = []

    async def record(_: AsyncSession, __: JobContext, payload: Payload) -> None:
        runs.append(payload["key"])

    await add_job(database, "orphan", kind="test.record")
    clock = Clock()
    # Simulate runner-a claiming the job and dying before finishing it.
    async with database.session() as session, session.begin():
        await session.execute(
            update(OutboxJob)
            .where(OutboxJob.dedupe_key == "orphan")
            .values(
                status="running",
                attempts=1,
                locked_by="runner-a",
                locked_until=clock.now + timedelta(minutes=5),
            )
        )

    runner_b = make_runner(
        context, {"test.record": JobHandler(run=record)}, name="runner-b", clock=clock
    )
    assert await runner_b.run_once() == 0, "still leased to runner-a"
    clock.advance(timedelta(minutes=5, seconds=1))
    assert await runner_b.run_once() == 1
    assert runs == ["orphan"]
    job = (await jobs_by_key(database))["orphan"]
    assert (job.status, job.attempts, job.locked_by) == ("done", 2, None)


async def test_a_runner_that_lost_its_lease_discards_its_result(
    database: Database, context: JobContext
) -> None:
    async def slow_write(session: AsyncSession, _: JobContext, __: Payload) -> None:
        session.add(Organization(name="Late result", industry="retail", country="IN"))
        # Meanwhile the lease expired and another runner claimed the job.
        async with database.session() as other, other.begin():
            await other.execute(
                update(OutboxJob).values(locked_by="runner-b", attempts=OutboxJob.attempts + 1)
            )

    await add_job(database, "slow", kind="test.slow")
    await make_runner(context, {"test.slow": JobHandler(run=slow_write)}).run_once()

    async with database.session() as session:
        assert list(await session.scalars(select(Organization.name))) == []
    job = (await jobs_by_key(database))["slow"]
    assert (job.status, job.locked_by) == ("running", "runner-b")


def test_backoff_schedule() -> None:
    assert [backoff(n).total_seconds() for n in range(1, 6)] == [2, 4, 8, 16, 32]
