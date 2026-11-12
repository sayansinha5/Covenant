from datetime import datetime
from typing import Any

from pydantic import Field

from app.domain.policy import WorkType
from app.models import Worker
from app.schemas.common import AmountIn, AmountOut, RequestModel, ResponseModel


class RegisterAgentRequest(RequestModel):
    base_url: str = Field(min_length=8, max_length=255)
    price: AmountIn
    categories: list[WorkType] = Field(min_length=1, max_length=4)
    auth_token: str | None = Field(default=None, min_length=8, max_length=200)


class RegisterHumanRequest(RequestModel):
    display_name: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=500)
    price: AmountIn
    categories: list[WorkType] = Field(min_length=1, max_length=4)


class WorkerOut(ResponseModel):
    id: str
    display_name: str
    description: str | None
    kind: str
    org_id: str
    org_name: str
    base_url: str | None
    categories: list[str]
    skills: list[dict[str, Any]]
    price: AmountOut
    currency: str
    status: str
    reputation: int
    jobs_completed: int
    verified_at: datetime | None


class VerificationStepOut(ResponseModel):
    step: str
    result: str
    detail: str | None
    created_at: datetime


class VerificationOut(ResponseModel):
    status: str
    steps: list[VerificationStepOut]


def worker_out(worker: Worker, org_name: str) -> WorkerOut:
    card = worker.agent_card or {}
    skills = card.get("skills")
    return WorkerOut(
        id=worker.id,
        display_name=worker.display_name,
        description=worker.description,
        kind=worker.kind,
        org_id=worker.org_id,
        org_name=org_name,
        base_url=worker.base_url,
        categories=list(worker.categories),
        skills=skills if isinstance(skills, list) else [],
        price=worker.price,
        currency=worker.currency,
        status=worker.status,
        reputation=worker.reputation,
        jobs_completed=worker.jobs_completed,
        verified_at=worker.verified_at,
    )
