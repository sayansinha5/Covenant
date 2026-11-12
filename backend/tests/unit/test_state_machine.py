from collections import deque

import pytest

from app.domain.state_machine import (
    ADMIN_RESOLUTION_TARGETS,
    TERMINAL_STATES,
    TRANSITIONS,
    Event,
    InvalidTransition,
    Job,
    Ledger,
    Notify,
    State,
    apply,
)

S, E = State, Event

# The transition table from the build spec (5.6), written out independently of the module.
SPEC_TABLE = {
    (S.DRAFT, E.MANDATE_OK): S.AWAITING_AGREEMENT,
    (S.DRAFT, E.MANDATE_NEEDS_APPROVAL): S.AWAITING_APPROVAL,
    (S.DRAFT, E.MANDATE_REJECTED): S.CANCELLED,
    (S.AWAITING_APPROVAL, E.APPROVED): S.AWAITING_AGREEMENT,
    (S.AWAITING_APPROVAL, E.REJECTED): S.CANCELLED,
    (S.AWAITING_APPROVAL, E.APPROVAL_EXPIRED): S.CANCELLED,
    (S.AWAITING_AGREEMENT, E.HIRER_AGREED): S.FUNDING,
    (S.AWAITING_AGREEMENT, E.HIRER_DECLINED): S.CANCELLED,
    (S.FUNDING, E.HOLD_CONFIRMED): S.FUNDED,
    (S.FUNDING, E.HOLD_FAILED): S.AWAITING_AGREEMENT,
    (S.FUNDED, E.DISPATCHED): S.SENT_TO_WORKER,
    (S.SENT_TO_WORKER, E.WORKER_ACCEPTED): S.IN_PROGRESS,
    (S.SENT_TO_WORKER, E.WORKER_DECLINED): S.EXPIRED,
    (S.SENT_TO_WORKER, E.ACCEPT_TIMEOUT): S.EXPIRED,
    (S.FUNDED, E.HIRER_CANCELLED): S.CANCELLED,
    (S.SENT_TO_WORKER, E.HIRER_CANCELLED): S.CANCELLED,
    (S.IN_PROGRESS, E.DELIVERED): S.VERIFYING,
    (S.IN_PROGRESS, E.DEADLINE_MISSED): S.EXPIRED,
    (S.VERIFYING, E.VERDICT_READY): S.VERDICT_ISSUED,
    (S.VERIFYING, E.VERIFY_GAVE_UP): S.NEEDS_ATTENTION,
    (S.VERDICT_ISSUED, E.SETTLE): S.SETTLING,
    (S.VERDICT_ISSUED, E.APPEAL_WINDOW_CLOSED): S.SETTLING,
    (S.VERDICT_ISSUED, E.WORKER_ACCEPTED_VERDICT): S.SETTLING,
    (S.VERDICT_ISSUED, E.APPEAL_OPENED): S.UNDER_APPEAL,
    (S.VERDICT_ISSUED, E.HIRER_DECIDED_BAND): S.SETTLING,
    (S.UNDER_APPEAL, E.APPEAL_ACCEPTED): S.SETTLING,
    (S.UNDER_APPEAL, E.APPEAL_UPHELD): S.SETTLING,
    (S.SETTLING, E.CAPTURED_FULL): S.SETTLED,
    (S.SETTLING, E.CAPTURED_PARTIAL): S.PARTIALLY_SETTLED,
    (S.SETTLING, E.VOIDED): S.REFUNDED,
}

NON_TERMINAL = [s for s in State if s not in TERMINAL_STATES and s is not S.NEEDS_ATTENTION]


def test_table_matches_the_spec_exactly() -> None:
    assert {key: t.target for key, t in TRANSITIONS.items()} == SPEC_TABLE


@pytest.mark.parametrize(("key", "target"), SPEC_TABLE.items(), ids=lambda v: str(v))
def test_apply_follows_each_row(key: tuple[State, Event], target: State) -> None:
    assert apply(*key).target is target


def _covered_by_a_rule(state: State, event: Event) -> bool:
    return (event is E.PAYPAL_INCONSISTENT and state in NON_TERMINAL) or (
        event is E.ADMIN_RESOLVED and state is S.NEEDS_ATTENTION
    )


@pytest.mark.parametrize(
    ("state", "event"),
    [
        (state, event)
        for state in State
        for event in Event
        if (state, event) not in SPEC_TABLE and not _covered_by_a_rule(state, event)
    ],
)
def test_everything_else_is_refused(state: State, event: Event) -> None:
    with pytest.raises(InvalidTransition):
        apply(state, event)


def test_terminal_states_never_move() -> None:
    for state in TERMINAL_STATES:
        for event in Event:
            with pytest.raises(InvalidTransition):
                apply(state, event, target=S.SETTLED if event is E.ADMIN_RESOLVED else None)


@pytest.mark.parametrize("state", NON_TERMINAL)
def test_paypal_inconsistency_parks_any_open_contract(state: State) -> None:
    transition = apply(state, E.PAYPAL_INCONSISTENT)
    assert transition.target is S.NEEDS_ATTENTION
    assert transition.notify == (Notify.HIRER, Notify.ADMIN)
    assert transition.jobs == ()


def test_admin_chooses_from_the_allowed_list_only() -> None:
    for target in State:
        if target in ADMIN_RESOLUTION_TARGETS:
            assert apply(S.NEEDS_ATTENTION, E.ADMIN_RESOLVED, target=target).target is target
        else:
            with pytest.raises(InvalidTransition):
                apply(S.NEEDS_ATTENTION, E.ADMIN_RESOLVED, target=target)
    with pytest.raises(InvalidTransition):
        apply(S.NEEDS_ATTENTION, E.ADMIN_RESOLVED)
    with pytest.raises(InvalidTransition):
        apply(S.FUNDED, E.ADMIN_RESOLVED, target=S.REFUNDED)


def test_admin_cannot_jump_into_a_money_moving_state() -> None:
    assert S.FUNDING not in ADMIN_RESOLUTION_TARGETS
    assert S.SETTLING not in ADMIN_RESOLUTION_TARGETS


def test_only_admin_resolution_takes_a_target() -> None:
    with pytest.raises(InvalidTransition, match="doesn't take a target"):
        apply(S.DRAFT, E.MANDATE_OK, target=S.FUNDED)


@pytest.mark.parametrize(
    ("key", "jobs", "ledger"),
    [
        ((S.AWAITING_AGREEMENT, E.HIRER_AGREED), (Job.CREATE_HOLD,), ()),
        ((S.FUNDING, E.HOLD_CONFIRMED), (Job.DISPATCH,), (Ledger.HELD,)),
        ((S.SENT_TO_WORKER, E.WORKER_DECLINED), (Job.VOID,), ()),
        ((S.SENT_TO_WORKER, E.ACCEPT_TIMEOUT), (Job.VOID,), ()),
        ((S.FUNDED, E.HIRER_CANCELLED), (Job.VOID,), ()),
        ((S.SENT_TO_WORKER, E.HIRER_CANCELLED), (Job.VOID,), ()),
        ((S.IN_PROGRESS, E.DELIVERED), (Job.VERIFY,), ()),
        ((S.IN_PROGRESS, E.DEADLINE_MISSED), (Job.VOID,), ()),
        ((S.VERDICT_ISSUED, E.APPEAL_OPENED), (Job.PREPARE_APPEAL,), ()),
        ((S.SETTLING, E.CAPTURED_FULL), (Job.SEND_PAYOUT,), (Ledger.CAPTURED, Ledger.FEE)),
        (
            (S.SETTLING, E.CAPTURED_PARTIAL),
            (Job.SEND_PAYOUT,),
            (Ledger.CAPTURED, Ledger.RELEASED, Ledger.FEE),
        ),
        ((S.SETTLING, E.VOIDED), (), (Ledger.RELEASED,)),
    ],
)
def test_side_effects(
    key: tuple[State, Event], jobs: tuple[Job, ...], ledger: tuple[Ledger, ...]
) -> None:
    transition = apply(*key)
    assert transition.jobs == jobs
    assert transition.ledger == ledger


def test_holds_start_only_on_agreement_and_voids_only_on_cancel_or_expiry() -> None:
    money_jobs = {Job.CREATE_HOLD, Job.VOID}
    for (source, _), transition in TRANSITIONS.items():
        if money_jobs & set(transition.jobs):
            assert transition.target in {S.FUNDING, S.EXPIRED, S.CANCELLED}, source


def test_notifications() -> None:
    assert apply(S.DRAFT, E.MANDATE_NEEDS_APPROVAL).notify == (Notify.OWNERS,)
    assert apply(S.FUNDING, E.HOLD_FAILED).notify == (Notify.HIRER,)
    assert apply(S.VERIFYING, E.VERIFY_GAVE_UP).notify == (Notify.HIRER, Notify.ADMIN)


def test_every_state_is_reachable_from_draft_and_can_finish() -> None:
    edges: dict[State, set[State]] = {state: set() for state in State}
    for (source, _), transition in TRANSITIONS.items():
        edges[source].add(transition.target)
    for state in NON_TERMINAL:
        edges[state].add(S.NEEDS_ATTENTION)
    edges[S.NEEDS_ATTENTION] |= ADMIN_RESOLUTION_TARGETS

    def reachable(start: State) -> set[State]:
        seen, queue = {start}, deque([start])
        while queue:
            for nxt in edges[queue.popleft()] - seen:
                seen.add(nxt)
                queue.append(nxt)
        return seen

    assert reachable(S.DRAFT) == set(State)
    for state in State:
        assert reachable(state) & TERMINAL_STATES, f"{state} can never finish"
