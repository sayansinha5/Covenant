"""The fields Covenant requires on an Agent Card, whether the SDK serves proto JSON
(camelCase, `supportedInterfaces`) or the classic card (`url`, `defaultInputModes`)."""

from dataclasses import dataclass
from typing import Any

from app.domain.policy import WORK_TYPES

MODES = ("application/json", "text/plain")


class AgentCardInvalid(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AgentCardInfo:
    name: str
    description: str
    url: str
    version: str
    protocol_version: str
    skills: tuple[dict[str, Any], ...]
    tags: frozenset[str]


def parse_agent_card(body: Any) -> AgentCardInfo:
    if not isinstance(body, dict):
        raise AgentCardInvalid("The agent card isn't a JSON object.")
    name = _text(body, "name")
    description = _text(body, "description")
    version = _text(body, "version")
    url, protocol_version = _endpoint(body)
    skills = body.get("skills")
    if not isinstance(skills, list) or not skills:
        raise AgentCardInvalid("The agent card has no skills.")
    parsed = tuple(_skill(skill) for skill in skills)
    modes = _modes(body, "defaultInputModes", "default_input_modes") + _modes(
        body, "defaultOutputModes", "default_output_modes"
    )
    if not any(mode in MODES for mode in modes):
        raise AgentCardInvalid("The agent must accept application/json or text/plain.")
    tags = frozenset(tag for skill in parsed for tag in skill["tags"])
    return AgentCardInfo(name, description, url, version, protocol_version, parsed, tags)


def categories_of(card: AgentCardInfo) -> list[str]:
    """Skill tags Covenant understands, in the standard category order."""
    return [category for category in WORK_TYPES if category in card.tags]


def _skill(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or not _text(value, "id", required=False):
        raise AgentCardInvalid("A skill needs an id, a name and tags.")
    tags = value.get("tags")
    if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
        raise AgentCardInvalid(f"Skill {value.get('id')!r} needs a list of tags.")
    return {"id": value["id"], "name": _text(value, "name"), "tags": tags}


def _endpoint(body: dict[str, Any]) -> tuple[str, str]:
    interfaces = body.get("supportedInterfaces") or body.get("supported_interfaces") or []
    if isinstance(interfaces, list):
        for interface in interfaces:
            if isinstance(interface, dict) and interface.get("url"):
                version = interface.get("protocolVersion") or interface.get("protocol_version")
                if isinstance(version, str) and version:
                    return str(interface["url"]), version
    url = body.get("url")
    version = body.get("protocolVersion") or body.get("protocol_version")
    if isinstance(url, str) and url and isinstance(version, str) and version:
        return url, version
    raise AgentCardInvalid("The agent card needs a URL and a protocol version.")


def _modes(body: dict[str, Any], *keys: str) -> list[str]:
    for key in keys:
        value = body.get(key)
        if isinstance(value, list):
            return [str(item) for item in value]
    return []


def _text(body: dict[str, Any], key: str, *, required: bool = True) -> str:
    value = body.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    if required:
        raise AgentCardInvalid(f"The agent card needs a {key}.")
    return ""
