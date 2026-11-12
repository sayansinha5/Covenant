from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.core.money import InvalidAmount, format_amount, parse_amount, round_down, round_half_up


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("40", Decimal("40.00")), ("40.5", Decimal("40.50")), (Decimal("0.01"), Decimal("0.01"))],
)
def test_parse_amount(raw: str | Decimal, expected: Decimal) -> None:
    assert parse_amount(raw) == expected


@pytest.mark.parametrize("raw", ["40.001", "abc", "NaN", "Infinity"])
def test_parse_amount_rejects_inexact_values(raw: str) -> None:
    with pytest.raises(InvalidAmount):
        parse_amount(raw)


def test_parse_amount_rejects_floats() -> None:
    with pytest.raises(InvalidAmount):
        parse_amount(0.1)  # type: ignore[arg-type]


def test_rounding_directions() -> None:
    assert round_down(Decimal("23.999")) == Decimal("23.99")
    assert round_half_up(Decimal("1.995")) == Decimal("2.00")
    assert round_half_up(Decimal("1.994")) == Decimal("1.99")


def test_format_amount_always_two_places() -> None:
    assert format_amount(Decimal("40")) == "40.00"
    assert format_amount(Decimal("0.5")) == "0.50"


@given(st.integers(min_value=1, max_value=1_000_000))
def test_format_parse_round_trip(cents: int) -> None:
    amount = Decimal(cents) / 100
    assert parse_amount(format_amount(amount)) == amount
