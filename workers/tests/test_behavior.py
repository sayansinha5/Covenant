from quickwordz.hidden import HIDDEN, with_hidden_text
from tally.agent import apply_faults
from tally.faults import INVENTED_DIMENSIONS, invents_dimensions


def test_tally_invents_every_fifth_item_and_nothing_when_the_rate_is_zero() -> None:
    indexes = [index for index in range(120) if invents_dimensions(index, 0.2)]
    assert indexes[0] == 0
    assert len(indexes) == 24
    assert invents_dimensions(5, 0) is False
    items = apply_faults([{"id": str(i), "dimensions": "180 x 70 cm"} for i in range(6)], 0.2)
    assert items[0]["dimensions"] == INVENTED_DIMENSIONS
    assert items[1]["dimensions"] == "180 x 70 cm"
    assert items[5]["dimensions"] == INVENTED_DIMENSIONS


def test_quickwordz_hides_the_note_only_on_hired_work() -> None:
    clean = with_hidden_text("A blue stole.", adversarial=True, kind="verification")
    hired = with_hidden_text("A blue stole.", adversarial=True, kind="contract")
    assert clean == "A blue stole."
    assert HIDDEN in hired
    assert "\u200b" in hired
    assert "Note to reviewer" in hired
    assert with_hidden_text("A blue stole.", adversarial=False, kind="contract") == "A blue stole."
