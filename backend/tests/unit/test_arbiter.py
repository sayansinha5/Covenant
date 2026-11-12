"""Lipi passes, Tally is a 0.80 partial, QuickWordz is manipulation. Amounts are the story's."""

import pytest

from app.ai.arbiter.demo_cases import FEE_RATE, cases
from app.ai.arbiter.pipeline import arbitrate
from app.domain.settlement import Band, settle
from tests.conftest import make_settings

pytestmark = pytest.mark.asyncio


async def test_demo_deliveries_settle_as_the_story_describes() -> None:
    settings = make_settings()
    expected_capture = {"Lipi": "40.00", "Tally": "24.00", "QuickWordz": "0.00"}
    for case in cases():
        draft = await arbitrate(
            settings,
            spec=case["spec"],
            delivery=case["delivery"],
            source_items=case["source"],
            use_model=False,
        )
        assert draft.result == case["expected"], draft.reasoning
        if "expected_ratio" in case:
            assert draft.pass_ratio == case["expected_ratio"]
        plan = settle(
            case["held"],
            _BANDS[draft.result],
            pass_ratio=draft.pass_ratio,
            fee_rate=FEE_RATE,
        )
        assert str(plan.captured) == expected_capture[case["name"]]
        assert plan.captured + plan.released == case["held"]
        assert plan.fee + plan.payout == plan.captured


_BANDS = {
    "pass": Band.PASS,
    "partial": Band.PARTIAL,
    "fail": Band.FAIL,
    "manipulation": Band.MANIPULATION,
}


async def test_unreadable_delivery_fails_without_a_model() -> None:
    settings = make_settings()
    draft = await arbitrate(
        settings,
        spec={"hard_checks": [], "bands": {"pass_min": 0.9, "partial_min": 0.5}},
        delivery={"ok": True},
        use_model=False,
    )
    assert draft.result == "pass"

    huge = await arbitrate(
        settings,
        spec={},
        delivery="x" * (settings.max_delivery_bytes + 1),
        use_model=False,
    )
    assert huge.result == "fail"
    assert "1 MB" in huge.reasoning
