"""How much of a hold to capture, release, keep as fee and pay out. Pure decimal maths; the
amounts here are the only ones the escrow jobs send to PayPal (never an LLM's numbers)."""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from app.core.money import CENT, round_down, round_half_up

ZERO = Decimal("0.00")


class Band(StrEnum):
    """The settlement band a verdict (or a person resolving `needs_review`) lands in."""

    PASS = "pass"  # noqa: S105
    PARTIAL = "partial"
    FAIL = "fail"
    MANIPULATION = "manipulation"


@dataclass(frozen=True, slots=True)
class Settlement:
    held: Decimal
    captured: Decimal
    released: Decimal
    fee: Decimal
    payout: Decimal

    @property
    def is_void(self) -> bool:
        return self.captured == ZERO

    @property
    def is_full(self) -> bool:
        return self.captured == self.held


def settle(held: Decimal, band: Band, *, pass_ratio: Decimal, fee_rate: Decimal) -> Settlement:
    """Pass captures everything; partial captures `held * ratio` rounded down to the cent (the
    hirer's favour); fail and manipulation release everything. A partial that rounds to $0.00
    is a void. Fee = captured * rate rounded half up; payout = captured - fee."""
    if held <= 0 or held != held.quantize(CENT):
        raise ValueError("held must be a positive amount in cents")
    if not ZERO <= pass_ratio <= 1:
        raise ValueError("pass_ratio must be between 0 and 1")
    if not ZERO <= fee_rate < 1:
        raise ValueError("fee_rate must be in [0, 1)")

    if band is Band.PASS:
        captured = held
    elif band is Band.PARTIAL:
        captured = round_down(held * pass_ratio)
    else:
        captured = ZERO

    fee = round_half_up(captured * fee_rate)
    return Settlement(
        held=held,
        captured=captured,
        released=held - captured,
        fee=fee,
        payout=captured - fee,
    )
