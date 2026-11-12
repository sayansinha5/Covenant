"""The contract lifecycle as data: a `(state, event) -> transition` table plus two rules that
apply to many states at once. Services call `apply` and persist the result; nothing else may
change a contract's state. Pure code: no I/O, no clock."""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum


class State(StrEnum):
    DRAFT = "draft"
    AWAITING_APPROVAL = "awaiting_approval"
    AWAITING_AGREEMENT = "awaiting_agreement"
    FUNDING = "funding"
    FUNDED = "funded"
    SENT_TO_WORKER = "sent_to_worker"
    IN_PROGRESS = "in_progress"
    VERIFYING = "verifying"
    VERDICT_ISSUED = "verdict_issued"
    UNDER_APPEAL = "under_appeal"
    SETTLING = "settling"
    SETTLED = "settled"
    PARTIALLY_SETTLED = "partially_settled"
    REFUNDED = "refunded"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    NEEDS_ATTENTION = "needs_attention"


class Event(StrEnum):
    MANDATE_OK = "mandate_ok"
    MANDATE_NEEDS_APPROVAL = "mandate_needs_approval"
    MANDATE_REJECTED = "mandate_rejected"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPROVAL_EXPIRED = "approval_expired"
    HIRER_AGREED = "hirer_agreed"
    HIRER_DECLINED = "hirer_declined"
    HOLD_CONFIRMED = "hold_confirmed"
    HOLD_FAILED = "hold_failed"
    DISPATCHED = "dispatched"
    WORKER_ACCEPTED = "worker_accepted"
    WORKER_DECLINED = "worker_declined"
    ACCEPT_TIMEOUT = "accept_timeout"
    HIRER_CANCELLED = "hirer_cancelled"
    DELIVERED = "delivered"
    DEADLINE_MISSED = "deadline_missed"
    VERDICT_READY = "verdict_ready"
    VERIFY_GAVE_UP = "verify_gave_up"
    SETTLE = "settle"
    APPEAL_WINDOW_CLOSED = "appeal_window_closed"
    WORKER_ACCEPTED_VERDICT = "worker_accepted_verdict"
    APPEAL_OPENED = "appeal_opened"
    HIRER_DECIDED_BAND = "hirer_decided_band"
    APPEAL_ACCEPTED = "appeal_accepted"
    APPEAL_UPHELD = "appeal_upheld"
    CAPTURED_FULL = "captured_full"
    CAPTURED_PARTIAL = "captured_partial"
    VOIDED = "voided"
    PAYPAL_INCONSISTENT = "paypal_inconsistent"
    ADMIN_RESOLVED = "admin_resolved"


class Job(StrEnum):
    """Outbox job kinds. The table below names the ones each transition enqueues; the rest are
    enqueued by the settlement step, by other jobs or on a schedule."""

    CREATE_HOLD = "escrow.create_hold"
    CAPTURE = "escrow.capture"
    VOID = "escrow.void"
    REAUTHORIZE_SCAN = "escrow.reauthorize_scan"
    REAUTHORIZE = "escrow.reauthorize"
    DISPATCH = "worker.dispatch"
    POLL = "worker.poll"
    VERIFY_WORKER = "worker.verify"
    VERIFY = "arbiter.verify"
    PREPARE_APPEAL = "appeal.prepare"
    CLOSE_APPEAL = "appeal.close"
    EXPIRE_APPROVAL = "approval.expire"
    SEND_PAYOUT = "payout.send"
    SYNC_PAYOUT = "payout.sync"
    PROCESS_WEBHOOK = "webhook.process"
    RECONCILE = "reconcile.run"


class Ledger(StrEnum):
    """Ledger directions a transition records."""

    HELD = "held"
    CAPTURED = "captured"
    RELEASED = "released"
    FEE = "fee"
    PAID_OUT = "paid_out"


class Notify(StrEnum):
    HIRER = "hirer"
    OWNERS = "owners"
    ADMIN = "admin"


TERMINAL_STATES = frozenset(
    {State.SETTLED, State.PARTIALLY_SETTLED, State.REFUNDED, State.CANCELLED, State.EXPIRED}
)

# Where an admin may move a contract after investigating it: states that describe a settled
# fact at PayPal or a safe restart point, never one that would trigger a second money movement
# by itself.
ADMIN_RESOLUTION_TARGETS = frozenset(
    {
        State.AWAITING_AGREEMENT,
        State.FUNDED,
        State.SETTLED,
        State.PARTIALLY_SETTLED,
        State.REFUNDED,
        State.CANCELLED,
        State.EXPIRED,
    }
)


class InvalidTransition(Exception):
    def __init__(self, state: State, event: Event, detail: str | None = None) -> None:
        self.state = state
        self.event = event
        super().__init__(detail or f"Event {event} is not allowed in state {state}.")


@dataclass(frozen=True, slots=True)
class Transition:
    """One row of the table. `jobs`, `ledger` and `notify` are the side effects the caller
    must write in the same transaction. Settlement transitions leave the capture-or-void job
    to the caller, because the amount comes from the settlement engine."""

    source: State
    event: Event
    target: State
    jobs: tuple[Job, ...] = ()
    ledger: tuple[Ledger, ...] = ()
    notify: tuple[Notify, ...] = ()


def _rows(
    sources: tuple[State, ...],
    events: tuple[Event, ...],
    target: State,
    *,
    jobs: tuple[Job, ...] = (),
    ledger: tuple[Ledger, ...] = (),
    notify: tuple[Notify, ...] = (),
) -> list[Transition]:
    return [
        Transition(source, event, target, jobs, ledger, notify)
        for source in sources
        for event in events
    ]


S, E = State, Event
_TABLE: list[Transition] = [
    *_rows((S.DRAFT,), (E.MANDATE_OK,), S.AWAITING_AGREEMENT),
    *_rows((S.DRAFT,), (E.MANDATE_NEEDS_APPROVAL,), S.AWAITING_APPROVAL, notify=(Notify.OWNERS,)),
    *_rows((S.DRAFT,), (E.MANDATE_REJECTED,), S.CANCELLED),
    *_rows((S.AWAITING_APPROVAL,), (E.APPROVED,), S.AWAITING_AGREEMENT),
    *_rows((S.AWAITING_APPROVAL,), (E.REJECTED, E.APPROVAL_EXPIRED), S.CANCELLED),
    *_rows((S.AWAITING_AGREEMENT,), (E.HIRER_AGREED,), S.FUNDING, jobs=(Job.CREATE_HOLD,)),
    *_rows((S.AWAITING_AGREEMENT,), (E.HIRER_DECLINED,), S.CANCELLED),
    *_rows(
        (S.FUNDING,),
        (E.HOLD_CONFIRMED,),
        S.FUNDED,
        jobs=(Job.DISPATCH,),
        ledger=(Ledger.HELD,),
    ),
    *_rows((S.FUNDING,), (E.HOLD_FAILED,), S.AWAITING_AGREEMENT, notify=(Notify.HIRER,)),
    *_rows((S.FUNDED,), (E.DISPATCHED,), S.SENT_TO_WORKER),
    *_rows((S.SENT_TO_WORKER,), (E.WORKER_ACCEPTED,), S.IN_PROGRESS),
    *_rows((S.SENT_TO_WORKER,), (E.WORKER_DECLINED, E.ACCEPT_TIMEOUT), S.EXPIRED, jobs=(Job.VOID,)),
    *_rows((S.FUNDED, S.SENT_TO_WORKER), (E.HIRER_CANCELLED,), S.CANCELLED, jobs=(Job.VOID,)),
    *_rows((S.IN_PROGRESS,), (E.DELIVERED,), S.VERIFYING, jobs=(Job.VERIFY,)),
    *_rows((S.IN_PROGRESS,), (E.DEADLINE_MISSED,), S.EXPIRED, jobs=(Job.VOID,)),
    *_rows((S.VERIFYING,), (E.VERDICT_READY,), S.VERDICT_ISSUED),
    *_rows(
        (S.VERIFYING,),
        (E.VERIFY_GAVE_UP,),
        S.NEEDS_ATTENTION,
        notify=(Notify.HIRER, Notify.ADMIN),
    ),
    *_rows(
        (S.VERDICT_ISSUED,),
        (E.SETTLE, E.APPEAL_WINDOW_CLOSED, E.WORKER_ACCEPTED_VERDICT, E.HIRER_DECIDED_BAND),
        S.SETTLING,
    ),
    *_rows((S.VERDICT_ISSUED,), (E.APPEAL_OPENED,), S.UNDER_APPEAL, jobs=(Job.PREPARE_APPEAL,)),
    *_rows((S.UNDER_APPEAL,), (E.APPEAL_ACCEPTED, E.APPEAL_UPHELD), S.SETTLING),
    *_rows(
        (S.SETTLING,),
        (E.CAPTURED_FULL,),
        S.SETTLED,
        jobs=(Job.SEND_PAYOUT,),
        ledger=(Ledger.CAPTURED, Ledger.FEE),
    ),
    *_rows(
        (S.SETTLING,),
        (E.CAPTURED_PARTIAL,),
        S.PARTIALLY_SETTLED,
        jobs=(Job.SEND_PAYOUT,),
        ledger=(Ledger.CAPTURED, Ledger.RELEASED, Ledger.FEE),
    ),
    *_rows((S.SETTLING,), (E.VOIDED,), S.REFUNDED, ledger=(Ledger.RELEASED,)),
]
del S, E

TRANSITIONS: Mapping[tuple[State, Event], Transition] = {(t.source, t.event): t for t in _TABLE}
if len(TRANSITIONS) != len(_TABLE):  # pragma: no cover - guards edits to the table
    raise RuntimeError("The contract transition table has a duplicate (state, event) row.")

_INCONSISTENT_NOTIFY = (Notify.HIRER, Notify.ADMIN)


def apply(state: State, event: Event, *, target: State | None = None) -> Transition:
    """Return the transition for `event` in `state`, or raise `InvalidTransition`.

    `target` is only used by `admin_resolved`, the one event whose destination is chosen by a
    person (from `ADMIN_RESOLUTION_TARGETS`)."""
    if event is Event.PAYPAL_INCONSISTENT:
        if state in TERMINAL_STATES or state is State.NEEDS_ATTENTION:
            raise InvalidTransition(state, event)
        return Transition(state, event, State.NEEDS_ATTENTION, notify=_INCONSISTENT_NOTIFY)

    if event is Event.ADMIN_RESOLVED:
        if state is not State.NEEDS_ATTENTION:
            raise InvalidTransition(state, event)
        if target not in ADMIN_RESOLUTION_TARGETS:
            raise InvalidTransition(
                state, event, f"An admin can't move a contract to {target or 'no state'}."
            )
        return Transition(state, event, target)

    if target is not None:
        raise InvalidTransition(state, event, f"Event {event} doesn't take a target state.")
    transition = TRANSITIONS.get((state, event))
    if transition is None:
        raise InvalidTransition(state, event)
    return transition
