import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Annotated, Any

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    PlainSerializer,
    StringConstraints,
)

from app.core.money import format_amount

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s.]+$")
MAX_AMOUNT = Decimal("1000000.00")


def _normalize_email(value: str) -> str:
    value = value.strip().lower()
    if not _EMAIL.match(value):
        raise ValueError("Enter a valid email address")
    return value


def _reject_float(value: Any) -> Any:
    if isinstance(value, float):
        raise ValueError('Send amounts as strings, like "40.00"')
    return value


Email = Annotated[str, StringConstraints(max_length=254), AfterValidator(_normalize_email)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
AmountIn = Annotated[
    Decimal,
    BeforeValidator(_reject_float),
    Field(gt=0, le=MAX_AMOUNT, max_digits=12, decimal_places=2),
]
AmountOut = Annotated[Decimal, PlainSerializer(format_amount, return_type=str)]


class RequestModel(BaseModel):
    """Base for every request body: unknown fields are rejected."""

    model_config = ConfigDict(extra="forbid", str_max_length=10_000)


class ResponseModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page[T](ResponseModel):
    items: list[T]
    page: int
    page_size: int
    total: int


@dataclass(frozen=True, slots=True)
class PageParams:
    page: int
    page_size: int

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size
