"""The Decide step. Bands, borders and money bands are code; a model never picks them."""

from decimal import Decimal

from app.domain.settlement import Band

ZERO = Decimal("0")
ONE = Decimal("1")


def quality_band(ratio: Decimal, *, pass_min: Decimal, partial_min: Decimal) -> str:
    """`pass` at or above pass_min, `partial` at or above partial_min, otherwise `fail`."""
    if ratio >= pass_min:
        return "pass"
    if ratio >= partial_min:
        return "partial"
    return "fail"


def near_border(
    ratio: Decimal, *, pass_min: Decimal, partial_min: Decimal, margin: Decimal
) -> bool:
    """True when the ratio sits within `margin` of a band edge (either side)."""
    return any(abs(ratio - edge) <= margin for edge in (pass_min, partial_min))


def money_band(result: str) -> Band | None:
    """The settlement band for a verdict. `needs_review` has none until a person decides."""
    if result == "pass":
        return Band.PASS
    if result == "partial":
        return Band.PARTIAL
    if result == "fail":
        return Band.FAIL
    if result == "manipulation":
        return Band.MANIPULATION
    return None
