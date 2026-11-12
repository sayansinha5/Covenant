from datetime import datetime
from typing import Annotated

from pydantic import Field, StringConstraints, ValidationInfo, field_validator

from app.core.security import PASSWORD_MAX_LENGTH
from app.domain.policy import WORK_TYPE_LABELS, WORK_TYPES, WorkType
from app.schemas.common import AmountIn, AmountOut, RequestModel, ResponseModel


class MandateCreate(RequestModel):
    monthly_budget: AmountIn
    per_task_cap: AmountIn
    approval_threshold: AmountIn
    allowed_work_types: list[WorkType] = Field(min_length=1)
    password: Annotated[str, StringConstraints(min_length=1, max_length=PASSWORD_MAX_LENGTH)]

    @field_validator("per_task_cap")
    @classmethod
    def _cap_within_budget(cls, value: AmountIn, info: ValidationInfo) -> AmountIn:
        budget = info.data.get("monthly_budget")
        if budget is not None and value > budget:
            raise ValueError("Maximum per task can't be more than the monthly budget")
        return value

    @field_validator("approval_threshold")
    @classmethod
    def _threshold_within_cap(cls, value: AmountIn, info: ValidationInfo) -> AmountIn:
        cap = info.data.get("per_task_cap")
        if cap is not None and value > cap:
            raise ValueError("The approval threshold can't be more than the maximum per task")
        return value

    @field_validator("allowed_work_types")
    @classmethod
    def _canonical_order(cls, value: list[WorkType]) -> list[WorkType]:
        return [work_type for work_type in WORK_TYPES if work_type in value]


class MandateOut(ResponseModel):
    id: str
    version: int
    monthly_budget: AmountOut
    per_task_cap: AmountOut
    approval_threshold: AmountOut
    currency: str
    allowed_work_types: list[str]
    signed_by_name: str
    signed_at: datetime
    is_active: bool


class MandateDefaults(ResponseModel):
    monthly_budget: AmountOut
    per_task_cap: AmountOut
    approval_threshold: AmountOut
    allowed_work_types: list[str]


class WorkTypeOption(ResponseModel):
    value: str
    label: str


class MandateOverview(ResponseModel):
    active: MandateOut | None
    defaults: MandateDefaults
    work_types: list[WorkTypeOption]


def work_type_options() -> list[WorkTypeOption]:
    return [
        WorkTypeOption(value=value, label=WORK_TYPE_LABELS[value].capitalize())
        for value in WORK_TYPES
    ]
