from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.domain.settlement import Band, settle

D = Decimal
held_amounts = st.integers(min_value=1, max_value=1_000_000_00).map(lambda c: D(c) / 100)
ratios = st.integers(min_value=0, max_value=10_000).map(lambda n: D(n) / 10_000)
fee_rates = st.integers(min_value=0, max_value=5_000).map(lambda n: D(n) / 10_000)


def test_story_amounts() -> None:
    # Tally's partial: 0.80 of $55 at a 10% fee.
    s = settle(D("55.00"), Band.PARTIAL, pass_ratio=D("0.80"), fee_rate=D("0.10"))
    assert (s.captured, s.released, s.fee, s.payout) == (
        D("44.00"),
        D("11.00"),
        D("4.40"),
        D("39.60"),
    )
    assert not s.is_full
    assert not s.is_void


def test_pass_captures_everything() -> None:
    s = settle(D("40.00"), Band.PASS, pass_ratio=D("0.95"), fee_rate=D("0.10"))
    assert (s.captured, s.released, s.fee, s.payout) == (D("40.00"), D("0"), D("4.00"), D("36.00"))
    assert s.is_full


@pytest.mark.parametrize("band", [Band.FAIL, Band.MANIPULATION])
def test_fail_and_manipulation_release_everything(band: Band) -> None:
    s = settle(D("55.00"), band, pass_ratio=D("1"), fee_rate=D("0.10"))
    assert (s.captured, s.released, s.fee, s.payout) == (D("0"), D("55.00"), D("0"), D("0"))
    assert s.is_void


def test_partial_rounds_down_in_the_hirers_favour() -> None:
    s = settle(D("10.01"), Band.PARTIAL, pass_ratio=D("0.5"), fee_rate=D("0"))
    assert s.captured == D("5.00")  # 5.005 → 5.00
    assert s.released == D("5.01")


def test_partial_that_rounds_to_zero_is_a_void() -> None:
    s = settle(D("0.01"), Band.PARTIAL, pass_ratio=D("0.5"), fee_rate=D("0.10"))
    assert s.is_void
    assert s.released == D("0.01")


def test_fee_rounds_half_up() -> None:
    s = settle(D("0.05"), Band.PASS, pass_ratio=D("1"), fee_rate=D("0.10"))
    assert s.fee == D("0.01")  # 0.005 → 0.01
    assert s.payout == D("0.04")


@pytest.mark.parametrize(
    ("held", "ratio", "rate"),
    [
        (D("0"), D("1"), D("0.1")),
        (D("1.001"), D("1"), D("0.1")),
        (D("1"), D("1.1"), D("0.1")),
        (D("1"), D("0.5"), D("1")),
    ],
)
def test_rejects_invalid_inputs(held: Decimal, ratio: Decimal, rate: Decimal) -> None:
    with pytest.raises(ValueError):
        settle(held, Band.PASS, pass_ratio=ratio, fee_rate=rate)


@given(held=held_amounts, band=st.sampled_from(Band), ratio=ratios, rate=fee_rates)
def test_money_is_conserved_and_exact(
    held: Decimal, band: Band, ratio: Decimal, rate: Decimal
) -> None:
    s = settle(held, band, pass_ratio=ratio, fee_rate=rate)
    for amount in (s.captured, s.released, s.fee, s.payout):
        assert amount >= 0
        assert amount == amount.quantize(D("0.01"))
    assert s.captured + s.released == held
    assert s.fee + s.payout == s.captured
    assert s.fee <= s.captured


@given(held=held_amounts, ratio=ratios, rate=fee_rates)
def test_partial_never_captures_more_than_earned(
    held: Decimal, ratio: Decimal, rate: Decimal
) -> None:
    s = settle(held, Band.PARTIAL, pass_ratio=ratio, fee_rate=rate)
    assert s.captured <= held * ratio
    assert held * ratio - s.captured < D("0.01")
