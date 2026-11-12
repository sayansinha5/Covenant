# D3 — Database outbox and a separate runner process

**Status:** accepted

**Context.** PayPal calls, worker dispatch and AI verification must survive restarts and never run
twice, without adding Redis or a broker.

**Options.** Celery + Redis; in-process background tasks; a DB outbox table polled by a runner.

**Decision.** An `outbox_jobs` table written in the same transaction as the state change, and a
`runner` process that claims jobs with `SELECT … FOR UPDATE SKIP LOCKED` (MySQL 8), with retries
and dead-lettering.

**Fallback.** `RUNNER_EMBEDDED=true` runs the same loop inside the API process.
