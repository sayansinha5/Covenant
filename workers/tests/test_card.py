from common.server import make_card


def test_card_names_the_skill() -> None:
    card = make_card(
        "Lipi", "Translates", "http://lipi:9101", [("translate", "Translate", ["translation"])]
    )
    assert card.name == "Lipi"
    assert card.skills[0].id == "translate"
    assert card.supported_interfaces[0].url == "http://lipi:9101"
