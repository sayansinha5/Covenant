"""The acceptance spec: the machine-checkable body of a contract, and its fingerprint."""

import hashlib
import json
from collections.abc import Mapping
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.ai.arbiter.hard_checks import HardCheck
from app.domain.policy import WorkType

WEIGHT_TOLERANCE = 0.001
Identifier = Annotated[str, StringConstraints(pattern=r"^[a-z0-9_-]{1,40}$")]


class Criterion(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: Identifier
    name: str = Field(min_length=1, max_length=60)
    description: str = Field(min_length=1, max_length=400)
    weight: float = Field(gt=0, le=1)


class Bands(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    pass_min: float = Field(gt=0, le=1)
    partial_min: float = Field(gt=0, le=1)


class AcceptanceSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    title: str = Field(min_length=1, max_length=200)
    work_type: WorkType
    deliverable_description: str = Field(min_length=1, max_length=1000)
    input_ref: str | None = None
    expected_item_count: int | None = Field(default=None, ge=1)
    item_schema: dict[str, Any] | None = None
    hard_checks: list[HardCheck] = Field(min_length=1, max_length=12)
    rubric: list[Criterion] = Field(min_length=2, max_length=5)
    item_pass_score: float = Field(ge=0, le=10)
    bands: Bands
    deadline_minutes: int = Field(gt=0)
    price: str = Field(pattern=r"^\d+\.\d{2}$")
    currency: str = Field(pattern=r"^[A-Z]{3}$")

    @model_validator(mode="after")
    def _consistent(self) -> "AcceptanceSpec":
        for kind, ids in (
            ("hard check", [c.id for c in self.hard_checks]),
            ("rubric criterion", [c.id for c in self.rubric]),
        ):
            if len(set(ids)) != len(ids):
                raise ValueError(f"Each {kind} needs a unique id")
        total = sum(c.weight for c in self.rubric)
        if abs(total - 1) > WEIGHT_TOLERANCE:
            raise ValueError(f"Rubric weights must sum to 1.0, not {total:g}")
        if self.bands.partial_min > self.bands.pass_min:
            raise ValueError("bands.partial_min must not exceed bands.pass_min")
        if self.expected_item_count is not None and not any(
            c.type == "item_count_equals" and c.params.get("count") == self.expected_item_count
            for c in self.hard_checks
        ):
            raise ValueError("expected_item_count needs a matching item_count_equals check")
        return self


def canonical_json(spec: Mapping[str, Any]) -> bytes:
    """Sorted keys, no whitespace, UTF-8: the exact bytes that are hashed and agreed."""
    return json.dumps(spec, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def fingerprint(spec: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(spec)).hexdigest()
