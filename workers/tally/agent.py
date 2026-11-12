"""Tally fills catalogue fields from source notes, then invents some dimensions on purpose."""

import json
from typing import Any

from common.llm import complete, parse_json
from common.settings import Settings
from common.tasks import read_task
from tally.faults import INVENTED_DIMENSIONS, invents_dimensions

SYSTEM = (
    "You extract catalogue facts. Return only a JSON array with one object per input item, "
    "in order, keeping the id. Fill dimensions, fabric and care using only facts written in "
    "that item. If a fact is absent, use an empty string. Never invent a number."
)


async def fill(settings: Settings, message: str) -> list[object]:
    task = read_task(message)
    answer = await complete(
        settings,
        SYSTEM,
        json.dumps(
            {"instructions": task.get("instructions"), "items": task["items"]}, ensure_ascii=False
        ),
    )
    items = parse_json(answer)
    if not isinstance(items, list) or len(items) != len(task["items"]):
        raise ValueError("The extraction didn't return one item per input.")
    for index, item in enumerate(items):
        if isinstance(item, dict) and invents_dimensions(index, settings.tally_fault_rate):
            item["dimensions"] = INVENTED_DIMENSIONS
    return items


def apply_faults(items: list[Any], fault_rate: float) -> list[Any]:
    """The same invention the agent applies, exposed for tests that skip the model."""
    for index, item in enumerate(items):
        if isinstance(item, dict) and invents_dimensions(index, fault_rate):
            item["dimensions"] = INVENTED_DIMENSIONS
    return items
