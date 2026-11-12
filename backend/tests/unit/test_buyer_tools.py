"""The in-app assistant can draft a contract. It has no tool that moves money."""

from types import SimpleNamespace

from app.ai.buyer.agent import build_tools


def test_the_assistant_cannot_fund() -> None:
    turn = SimpleNamespace(
        session=None,
        settings=None,
        paypal=None,
        org_id="org",
        user_id="user",
        org_name="Kantha",
        assistant_name="Mira",
        actor_name="Riya",
        cards=[],
        steps=[],
        actor=None,
    )
    names = {tool.name for tool in build_tools(turn)}  # type: ignore[arg-type]
    assert "fund" not in names
    assert "fund_contract" not in names
    assert "agree" not in names
    assert {"search_workers", "draft_contract", "get_mandate", "cancel_contract"} <= names
