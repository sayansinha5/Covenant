"""Show the three Arbiter outcomes and the capture amounts the settlement engine would send.

    python scripts/arbiter_demo.py

This uses the code judge (hard checks and the manipulation scan decide the band). A funded
contract uses the configured model as well; the band is still chosen here in code.
"""

import asyncio
from decimal import Decimal

from app.ai.arbiter.demo_cases import FEE_RATE, cases
from app.ai.arbiter.pipeline import arbitrate
from app.core.config import ConfigurationError, load_settings
from app.domain.settlement import Band, settle

BANDS = {
    "pass": Band.PASS,
    "partial": Band.PARTIAL,
    "fail": Band.FAIL,
    "manipulation": Band.MANIPULATION,
}


async def main() -> None:
    try:
        settings = load_settings()
    except ConfigurationError as exc:
        raise SystemExit(str(exc)) from None
    failed = False
    expected = {"Lipi": "pass", "Tally": "partial", "QuickWordz": "manipulation"}
    for case in cases():
        draft = await arbitrate(
            settings,
            spec=case["spec"],
            delivery=case["delivery"],
            source_items=case["source"],
            use_model=False,
        )
        plan = settle(
            case["held"], BANDS[draft.result], pass_ratio=draft.pass_ratio, fee_rate=FEE_RATE
        )
        mark = "ok" if draft.result == expected[case["name"]] else "UNEXPECTED"
        if mark != "ok":
            failed = True
        print(
            f"{case['name']}: {draft.result} ratio {draft.pass_ratio} "
            f"capture {plan.captured} release {plan.released} fee {plan.fee} "
            f"payout {plan.payout} [{mark}]"
        )
        if case["name"] == "Tally" and draft.pass_ratio != Decimal("0.8000"):
            failed = True
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
