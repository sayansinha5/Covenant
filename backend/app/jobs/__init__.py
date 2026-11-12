"""Outbox job handlers, one module per job area, registered in `HANDLERS` by kind."""

from collections.abc import Mapping
from datetime import timedelta

from app.domain.state_machine import Job
from app.jobs import (
    appeal,
    capture,
    dispatch,
    hold,
    payout,
    reauthorize,
    reconcile,
    verify,
    void,
    webhook,
    worker_verify,
)
from app.jobs.base import JobHandler
from app.services.reconcile import INTERVAL as RECONCILE_INTERVAL

HANDLERS: Mapping[str, JobHandler] = {
    Job.CREATE_HOLD: hold.HANDLER,
    Job.CAPTURE: capture.HANDLER,
    Job.VOID: void.HANDLER,
    Job.REAUTHORIZE_SCAN: reauthorize.SCAN_HANDLER,
    Job.REAUTHORIZE: reauthorize.HANDLER,
    Job.DISPATCH: dispatch.HANDLER,
    Job.POLL: dispatch.POLL_HANDLER,
    Job.SEND_PAYOUT: payout.SEND_HANDLER,
    Job.SYNC_PAYOUT: payout.SYNC_HANDLER,
    Job.PROCESS_WEBHOOK: webhook.HANDLER,
    Job.RECONCILE: reconcile.HANDLER,
    Job.VERIFY_WORKER: worker_verify.HANDLER,
    Job.VERIFY: verify.HANDLER,
    Job.PREPARE_APPEAL: appeal.PREPARE_HANDLER,
    Job.CLOSE_APPEAL: appeal.CLOSE_HANDLER,
    Job.EXPIRE_APPROVAL: appeal.EXPIRE_HANDLER,
}

SCHEDULES: Mapping[str, timedelta] = {
    Job.REAUTHORIZE_SCAN: reauthorize.SCAN_INTERVAL,
    Job.RECONCILE: RECONCILE_INTERVAL,
}
