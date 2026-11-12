from datetime import UTC, datetime
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.domain.policy import (
    WORK_TYPES,
    MandateTerms,
    Outcome,
    evaluate,
    month_start,
    usd,
)

RIYA = MandateTerms(
    version=3,
    monthly_budget=Decimal("300.00"),
    per_task_cap=Decimal("60.00"),
    approval_threshold=Decimal("40.00"),
    allowed_work_types=frozenset(WORK_TYPES),
)


def check(
    amount: str,
    *,
    mandate: MandateTerms | None = RIYA,
    work_type: str = "translation",
    committed: str = "0.00",
    connected: bool = True,
    approved: bool = False,
):
    return evaluate(
        mandate,
        amount=Decimal(amount),
        work_type=work_type,
        committed_this_month=Decimal(committed),
        funding_connected=connected,
        approved=approved,
    )


def test_1_missing_or_inactive_mandate_rejects() -> None:
    assert check("10.00", mandate=None).code == "MANDATE_MISSING"
    inactive = MandateTerms(1, Decimal(300), Decimal(60), Decimal(40), frozenset(WORK_TYPES), False)
    decision = check("10.00", mandate=inactive)
    assert (decision.outcome, decision.code) == (Outcome.REJECTED, "MANDATE_MISSING")


def test_2_work_type_must_be_allowed() -> None:
    only_translation = MandateTerms(
        1, Decimal(300), Decimal(60), Decimal(40), frozenset({"translation"})
    )
    decision = check("10.00", mandate=only_translation, work_type="design")
    assert decision.code == "MANDATE_WORK_TYPE"
    assert decision.reason == "Your mandate doesn't allow design work."


def test_3_amount_over_per_task_cap_rejects() -> None:
    decision = check("60.01")
    assert decision.code == "MANDATE_OVER_TASK_CAP"
    assert decision.reason == "This contract is $60.01. Your mandate allows at most $60 per task."
    assert check("500.00").outcome is Outcome.REJECTED  # the agent "deciding" to fund $500


def test_4_monthly_budget_counts_committed_spend() -> None:
    assert check("40.00", committed="260.00").allowed
    decision = check("40.00", committed="260.01")
    assert decision.code == "MANDATE_OVER_BUDGET"
    assert decision.reason == (
        "This contract is $40 but only $39.99 of your $300 monthly budget is left."
    )
    assert "only $0 of" in check("10.00", committed="305.00").reason


def test_5_amount_over_threshold_needs_approval_not_rejection() -> None:
    decision = check("55.00")
    assert decision.outcome is Outcome.NEEDS_APPROVAL
    assert decision.reason == "This contract is $55. Your mandate asks for approval above $40."
    assert check("40.00").allowed  # the threshold itself doesn't need approval
    assert check("55.00", approved=True).allowed


def test_6_funding_account_must_be_connected() -> None:
    decision = check("10.00", connected=False)
    assert (decision.outcome, decision.code) == (Outcome.REJECTED, "FUNDING_NOT_CONNECTED")


def test_checks_run_in_order_and_first_failure_wins() -> None:
    # Fails 2, 3, 4, 5 and 6 at once: the work type is reported.
    only_design = MandateTerms(1, Decimal(300), Decimal(60), Decimal(40), frozenset({"design"}))
    everything_wrong = check("500.00", mandate=only_design, committed="300.00", connected=False)
    assert everything_wrong.code == "MANDATE_WORK_TYPE"
    assert check("500.00", committed="300.00", connected=False).code == "MANDATE_OVER_TASK_CAP"
    assert check("50.00", committed="290.00", connected=False).code == "MANDATE_OVER_BUDGET"
    # Approval comes before the funding check, so the owner hears about it first.
    assert check("50.00", connected=False).code == "APPROVAL_REQUIRED"
    assert check("50.00", connected=False, approved=True).code == "FUNDING_NOT_CONNECTED"


def test_decision_records_the_mandate_version() -> None:
    assert check("10.00").mandate_version == 3
    assert check("10.00", mandate=None).mandate_version is None


def test_non_positive_amount_is_a_programming_error() -> None:
    with pytest.raises(ValueError):
        check("0.00")


@given(
    amount=st.decimals(min_value="0.01", max_value="1000", places=2),
    committed=st.decimals(min_value="0", max_value="1000", places=2),
)
def test_allowed_spend_never_breaks_cap_or_budget(amount: Decimal, committed: Decimal) -> None:
    decision = evaluate(
        RIYA,
        amount=amount,
        work_type="copywriting",
        committed_this_month=committed,
        funding_connected=True,
        approved=True,
    )
    if decision.allowed:
        assert amount <= RIYA.per_task_cap
        assert committed + amount <= RIYA.monthly_budget


def test_helpers() -> None:
    assert usd(Decimal("40.00")) == "$40"
    assert usd(Decimal("1250.5")) == "$1,250.50"
    moment = datetime(2026, 11, 3, 15, 4, 5, 6, tzinfo=UTC)
    assert month_start(moment) == datetime(2026, 11, 1, tzinfo=UTC)
