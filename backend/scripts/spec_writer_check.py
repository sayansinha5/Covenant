"""Manual Spec Writer check (build step 9).

Turns Riya's German translation request and `tests/fixtures/stoles.json` into an acceptance
spec with the configured AI provider, then prints the spec and its fingerprint. With LangSmith
on (LANGSMITH_TRACING=true and a key), the run appears in LANGSMITH_PROJECT under the printed ID.

    python scripts/spec_writer_check.py
"""

import asyncio
import sys
from decimal import Decimal
from pathlib import Path

from app.ai import tracing
from app.ai.factory import AINotConfigured
from app.ai.spec_writer.source import parse_rows
from app.ai.spec_writer.spec import fingerprint
from app.ai.spec_writer.writer import SourceFile, SpecRequest, write_spec
from app.ai.structured import StructuredOutputFailed
from app.core.config import ConfigurationError, load_settings

STOLES = Path(__file__).parents[1] / "tests" / "fixtures" / "stoles.json"
RIYA_REQUEST = (
    "Translate my 40 stole listings into German for a Berlin boutique. Keep the tone warm "
    "and artisanal. Budget around $40. Listings attached."
)


async def main() -> None:
    try:
        settings = load_settings()
    except ConfigurationError as exc:
        sys.exit(f"Covenant settings are invalid.\n{exc}")
    rows = parse_rows(STOLES.read_bytes(), STOLES.name)
    request = SpecRequest(
        request_text=RIYA_REQUEST,
        work_type="translation",
        worker_name="Lipi",
        worker_kind="agent",
        price=Decimal("40.00"),
        currency=settings.currency,
        source=SourceFile(file_id=None, name=STOLES.name, rows=rows),
    )
    try:
        written = await write_spec(settings, request, org_id="spec-writer-check")
    except (AINotConfigured, StructuredOutputFailed) as exc:
        sys.exit(f"FAIL: {exc}")
    finally:
        tracing.flush()

    spec = written.spec
    print(f"Title:            {spec.title}")
    print(f"Deliverable:      {spec.deliverable_description}")
    print(f"Expected items:   {spec.expected_item_count} (source rows: {len(rows)})")
    print("Must have:")
    for check in spec.hard_checks:
        print(f"  - {check.describe()}  [{check.type}, {check.applies_to}]")
    print("Quality bar:")
    for criterion in spec.rubric:
        print(f"  - {criterion.name} {criterion.weight:.0%}: {criterion.description}")
    print(f"Price:            {spec.price} {spec.currency}, deadline {spec.deadline_minutes} min")
    print(f"Fingerprint:      {fingerprint(spec.model_dump(mode='json'))[:12]}")
    print(f"Prompt version:   {written.prompt_version}")
    if written.run_id:
        print(f"LangSmith run:    {written.run_id} (project {settings.langsmith_project})")
    else:
        print("LangSmith run:    tracing is off (set LANGSMITH_TRACING=true and LANGSMITH_API_KEY)")
    if spec.expected_item_count != len(rows):
        sys.exit("FAIL: the expected item count doesn't match the file")
    print("OK")


if __name__ == "__main__":
    asyncio.run(main())
