"""Deterministic manipulation scan: hidden text and reviewer-directed phrases.

A model classifier can add a flag later. These hits are enough on their own, and they don't
depend on a provider being configured."""

import json
import re
from typing import Any

from app.ai.arbiter.hard_checks import CSS_HIDDEN, HTML_COMMENT, ZERO_WIDTH

# Kept in the prompt and the tests. High severity: any one hit flags the delivery.
PHRASES: tuple[str, ...] = (
    "note to reviewer",
    "ignore previous instructions",
    "give this a perfect score",
    "pre-approved",
    "preapproved",
    "reviewer_score",
)
QUOTE = 180


def scan(delivery: Any) -> dict[str, Any] | None:
    """A high-severity hit, or None. `evidence` is a short quote safe to show a person."""
    text = _flatten(delivery)
    folded = text.casefold()
    for phrase in PHRASES:
        at = folded.find(phrase)
        if at >= 0:
            return _hit("phrase", phrase, text[at : at + QUOTE])
    if match := ZERO_WIDTH.search(text):
        return _hit("hidden_text", "invisible characters", _around(text, match))
    if match := HTML_COMMENT.search(text):
        return _hit("hidden_text", "an HTML comment", match.group()[:QUOTE])
    if match := CSS_HIDDEN.search(text):
        return _hit("hidden_text", "text hidden with CSS", match.group()[:QUOTE])
    return None


def _hit(kind: str, label: str, quote: str) -> dict[str, Any]:
    visible = re.sub(r"\s+", " ", quote).strip()
    return {
        "flagged": True,
        "severity": "high",
        "kind": kind,
        "evidence": f"Found {label}: {visible}",
    }


def _around(text: str, match: re.Match[str]) -> str:
    start = max(0, match.start() - 40)
    return text[start : match.end() + 80]


def _flatten(delivery: Any) -> str:
    try:
        return json.dumps(delivery, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(delivery)
