"""Exact decimal money helpers. Money never touches float anywhere in Covenant."""

from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal, InvalidOperation

CENT = Decimal("0.01")


class InvalidAmount(ValueError):
    pass


def parse_amount(value: str | Decimal | int) -> Decimal:
    """Parse an amount that must already be exact to the cent (API input, PayPal responses)."""
    if isinstance(value, float):
        raise InvalidAmount("Amounts must not be floats")
    try:
        amount = Decimal(value)
    except (InvalidOperation, TypeError) as exc:
        raise InvalidAmount(f"Not a valid amount: {value!r}") from exc
    if not amount.is_finite():
        raise InvalidAmount(f"Not a finite amount: {value!r}")
    if amount != amount.quantize(CENT):
        raise InvalidAmount(f"Amount has more than 2 decimal places: {value!r}")
    return amount.quantize(CENT)


def round_down(amount: Decimal) -> Decimal:
    """Round to the cent towards zero (capture amounts: always in the hirer's favour)."""
    return amount.quantize(CENT, rounding=ROUND_DOWN)


def round_half_up(amount: Decimal) -> Decimal:
    """Round to the cent, halves away from zero (platform fee)."""
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


def format_amount(amount: Decimal) -> str:
    """Wire format used by the API and PayPal: plain string with exactly two decimals."""
    return f"{parse_amount(amount):.2f}"
