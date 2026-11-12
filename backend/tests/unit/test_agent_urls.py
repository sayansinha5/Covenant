import socket

import pytest

from app.integrations.a2a.card import AgentCardInvalid, parse_agent_card
from app.integrations.a2a.ssrf import AgentUrlRefused, check_agent_url

CARD = {
    "name": "Lipi",
    "description": "Translates listings.",
    "version": "0.1.0",
    "supportedInterfaces": [
        {"url": "http://lipi:9101", "protocolBinding": "JSONRPC", "protocolVersion": "1.0"}
    ],
    "defaultInputModes": ["application/json"],
    "defaultOutputModes": ["application/json"],
    "skills": [{"id": "translate", "name": "Translate", "tags": ["translation", "other"]}],
}


def test_metadata_address_is_refused_even_if_the_host_is_listed() -> None:
    with pytest.raises(AgentUrlRefused, match="metadata"):
        check_agent_url("http://169.254.169.254/latest", ["169.254.169.254"])


def test_a_host_outside_the_allow_list_is_refused() -> None:
    with pytest.raises(AgentUrlRefused, match="isn't a host"):
        check_agent_url("https://example.com/agent", ["lipi"])


def test_userinfo_and_other_schemes_are_refused() -> None:
    with pytest.raises(AgentUrlRefused):
        check_agent_url("http://user:pw@lipi:9101", ["lipi"])
    with pytest.raises(AgentUrlRefused):
        check_agent_url("file:///etc/passwd", ["lipi"])


def test_an_allowed_host_may_resolve_to_a_private_address(monkeypatch: pytest.MonkeyPatch) -> None:
    real = socket.getaddrinfo

    def resolve(host: str, *args: object, **kwargs: object) -> list[object]:
        if host == "lipi":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("172.18.0.5", 0))]
        return real(host, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(socket, "getaddrinfo", resolve)
    assert check_agent_url("http://lipi:9101", ["lipi"]) == "lipi"


def test_agent_card_accepts_the_sdk_shape_and_rejects_a_card_without_skills() -> None:
    card = parse_agent_card(CARD)
    assert (card.name, card.protocol_version, "translation" in card.tags) == ("Lipi", "1.0", True)
    with pytest.raises(AgentCardInvalid, match="skills"):
        parse_agent_card({**CARD, "skills": []})
