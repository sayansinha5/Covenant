"""Score the labelled set with the code judge and print accuracy.

python -m evals.arbiter.run
"""

import asyncio
from collections import Counter

from app.ai.arbiter.pipeline import arbitrate
from app.core.config import ConfigurationError, load_settings
from evals.arbiter.cases import labelled_cases


async def main() -> None:
    try:
        settings = load_settings()
    except ConfigurationError as exc:
        raise SystemExit(str(exc)) from None
    cases = labelled_cases()
    confusion: Counter[tuple[str, str]] = Counter()
    groups: dict[str, list[bool]] = {}
    for case in cases:
        draft = await arbitrate(
            settings,
            spec=case["spec"],
            delivery=case["delivery"],
            source_items=case["source"],
            use_model=False,
        )
        ok = draft.result == case["expected"]
        if case.get("ratio") and str(draft.pass_ratio) != case["ratio"]:
            ok = False
        groups.setdefault(case["group"], []).append(ok)
        confusion[(case["expected"], draft.result)] += 1
    total = len(cases)
    correct = sum(hit for rows in groups.values() for hit in rows)
    honest = [hit for name, rows in groups.items() if name != "adversarial" for hit in rows]
    adversarial = groups.get("adversarial", [])
    print(f"cases {total}")
    print(f"accuracy {correct / total:.2%}")
    for name, rows in groups.items():
        print(f"{name} {sum(rows)}/{len(rows)}")
    print("confusion expected->actual")
    for pair, count in sorted(confusion.items()):
        print(f"  {pair[0]} -> {pair[1]}: {count}")
    manipulation_recall = sum(adversarial) / len(adversarial) if adversarial else 0
    false_positives = sum(
        count
        for (expected, actual), count in confusion.items()
        if expected != "manipulation" and actual == "manipulation"
    )
    print(f"manipulation recall {manipulation_recall:.2%}")
    print(f"manipulation false positives on honest cases {false_positives}/{len(honest)}")
    if correct != total:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
