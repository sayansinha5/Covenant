"""Versioned prompt templates: `<name>.v<N>.md`, each with a `## System` and a `## User`
section. Placeholders use `$name` (string.Template), so JSON examples need no escaping."""

import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from string import Template

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

PROMPT_DIR = Path(__file__).parent
FILE_NAME = re.compile(r"^(?P<name>[a-z_]+)\.v(?P<version>\d+)\.md$")
SECTION = re.compile(r"^## (System|User)\s*$", re.MULTILINE)


class PromptError(LookupError):
    pass


@dataclass(frozen=True, slots=True)
class Prompt:
    name: str
    version: int
    system: Template
    user: Template

    @property
    def version_id(self) -> str:
        """Stored on every result the prompt produced, e.g. `spec_writer.v1`."""
        return f"{self.name}.v{self.version}"

    def messages(self, **values: object) -> list[BaseMessage]:
        text = {key: str(value) for key, value in values.items()}
        return [
            SystemMessage(self.system.substitute(text)),
            HumanMessage(self.user.substitute(text)),
        ]


@cache
def load_prompt(name: str, version: int | None = None) -> Prompt:
    """The given version of a prompt, or the newest one."""
    versions = {
        int(match["version"]): path
        for path in PROMPT_DIR.glob(f"{name}.v*.md")
        if (match := FILE_NAME.match(path.name)) and match["name"] == name
    }
    if not versions:
        raise PromptError(f"No prompt named {name!r} in {PROMPT_DIR}")
    chosen = max(versions) if version is None else version
    if chosen not in versions:
        raise PromptError(f"Prompt {name!r} has no version {chosen}")
    return _parse(name, chosen, versions[chosen].read_text(encoding="utf-8"))


def _parse(name: str, version: int, text: str) -> Prompt:
    parts = SECTION.split(text)
    sections = dict(zip(parts[1::2], (part.strip() for part in parts[2::2]), strict=True))
    if set(sections) != {"System", "User"}:
        raise PromptError(f"{name}.v{version}.md needs exactly one ## System and one ## User")
    return Prompt(name, version, Template(sections["System"]), Template(sections["User"]))
