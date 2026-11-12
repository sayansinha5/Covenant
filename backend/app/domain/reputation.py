"""How a verdict moves a worker's reputation. Pure: the job applies the numbers."""

COMPLETED = frozenset({"pass", "partial", "fail", "manipulation"})
_DELTA = {"pass": 2, "partial": 0, "fail": -5, "manipulation": -20}


def next_reputation(current: int, result: str) -> int:
    """Pass creeps up, a fail drops a little, manipulation drops hard. Clamped to 0-100."""
    return min(100, max(0, current + _DELTA.get(result, 0)))


def counts_as_completed(result: str) -> bool:
    return result in COMPLETED


def suspension_reason(result: str) -> str | None:
    if result == "manipulation":
        return "A delivery tried to manipulate the Arbiter."
    return None
