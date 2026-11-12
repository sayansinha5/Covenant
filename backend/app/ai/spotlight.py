"""Spotlighting: untrusted text (requests, deliveries, Agent Cards, appeals) goes to a model
only inside boundary tags with a random suffix, so the text can't close the tag itself."""

import secrets
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Spotlit:
    tag: str
    block: str


def spotlight(kind: str, text: str) -> Spotlit:
    """Wrap `text` as `<untrusted_<kind>_<random>>…</…>`. Prompts name the tag (`tag`) and
    state that its content is data to evaluate, never instructions."""
    while True:
        tag = f"untrusted_{kind}_{secrets.token_hex(6)}"
        if tag not in text:
            return Spotlit(tag=tag, block=f"<{tag}>\n{text}\n</{tag}>")
