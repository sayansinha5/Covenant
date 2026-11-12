from datetime import datetime
from typing import Annotated, Any

from pydantic import StringConstraints

from app.schemas.common import AmountOut, RequestModel, ResponseModel

Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=255)]


class ModerationRequest(RequestModel):
    reason: Reason


class AdminWorkerOut(ResponseModel):
    id: str
    display_name: str
    kind: str
    org_id: str
    org_name: str
    base_url: str | None
    categories: list[str]
    price: AmountOut
    currency: str
    status: str
    reputation: int
    suspended_reason: str | None
    created_at: datetime


class WebhookEventOut(ResponseModel):
    id: str
    paypal_event_id: str | None
    claimed_event_id: str | None
    event_type: str
    resource_id: str | None
    verified: bool
    processed: bool
    result: str | None
    outcome: str | None
    error: str | None
    contract_id: str | None
    contract_number: str | None
    received_at: datetime
    processed_at: datetime | None


class ReconciliationRunOut(ResponseModel):
    id: str
    trigger: str
    status: str
    checked: int
    in_sync: int
    fixed: int
    needs_attention: int
    errors: int
    findings: list[dict[str, Any]]
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
