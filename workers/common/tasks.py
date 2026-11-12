"""The JSON message Covenant sends: instructions plus the items to work on."""

import json
from typing import Any


class TaskRejectedError(ValueError):
    pass


def read_task(text: str) -> dict[str, Any]:
    try:
        body = json.loads(text)
    except json.JSONDecodeError as exc:
        raise TaskRejectedError("The message isn't JSON.") from exc
    if not isinstance(body, dict) or not isinstance(body.get("items"), list):
        raise TaskRejectedError("The message needs an items array.")
    return body
