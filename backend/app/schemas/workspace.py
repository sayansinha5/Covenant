"""Responses for contracts, the ledger, overview, notifications, earnings and API keys."""

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from app.schemas.common import AmountIn, AmountOut, RequestModel, ResponseModel

BandName = Literal["pass", "partial", "fail"]


class ContractListItem(ResponseModel):
    id: str
    number: str
    title: str
    state: str
    amount: AmountOut
    currency: str
    worker_name: str
    role: str
    updated_at: datetime


class TimelineEvent(ResponseModel):
    id: str
    event: str
    message: str
    created_at: datetime
    actor_type: str


class VerdictOut(ResponseModel):
    result: str
    pass_ratio: str
    overall_score: str
    reasoning: str
    item_results: list[dict[str, Any]]
    manipulation: dict[str, Any] | None


class EscrowOut(ResponseModel):
    status: str
    amount_held: AmountOut
    amount_captured: AmountOut
    amount_released: AmountOut
    settlement: dict[str, Any] | None


class AppealOut(ResponseModel):
    id: str
    status: str
    argument: str
    memo: dict[str, Any] | None
    decision_note: str | None


class ContractDetail(ContractListItem):
    work_type: str
    request_text: str
    spec: dict[str, Any] | None
    spec_fingerprint: str | None
    deadline_at: datetime | None
    appeal_window_ends_at: datetime | None
    worker_kind: str
    hirer_name: str
    provider_name: str
    events: list[TimelineEvent]
    delivery: Any | None
    verdict: VerdictOut | None
    escrow: EscrowOut | None
    appeal: AppealOut | None


class DraftIn(RequestModel):
    worker_id: str
    request_text: str = Field(min_length=1, max_length=4000)
    budget: AmountIn | None = None


class DeliveryIn(RequestModel):
    content: Any
    notes: str = ""
    file_ids: list[str] = Field(default_factory=list)


class AppealIn(RequestModel):
    argument: str = Field(min_length=50, max_length=4000)


class BandIn(RequestModel):
    band: BandName


class AppealDecisionIn(RequestModel):
    accept: bool
    note: str | None = Field(default=None, max_length=500)


class ChangeIn(RequestModel):
    change_request: str = Field(min_length=1, max_length=2000)


class ApprovalOut(ResponseModel):
    id: str
    contract_id: str
    reason: str
    status: str
    expires_at: datetime


class LedgerRow(ResponseModel):
    id: str
    contract_id: str
    contract_number: str | None = None
    direction: str
    entry_type: str
    amount: AmountOut
    currency: str
    paypal_reference: str | None = None
    actor_type: str
    created_at: datetime


class OverviewOut(ResponseModel):
    by_state: dict[str, int]
    captured_this_month: AmountOut
    currently_held: AmountOut


class NotificationOut(ResponseModel):
    id: str
    kind: str
    title: str
    body: str
    link: str | None
    read_at: datetime | None
    created_at: datetime


class PayoutOut(ResponseModel):
    id: str
    contract_id: str
    gross: AmountOut
    fee: AmountOut
    net: AmountOut
    currency: str
    status: str
    created_at: datetime


class EarningsOut(ResponseModel):
    paid: AmountOut
    pending: AmountOut
    payouts: list[PayoutOut]


class ApiKeyOut(ResponseModel):
    id: str
    name: str
    prefix: str
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None


class ApiKeyCreated(ApiKeyOut):
    key: str


class ApiKeyIn(RequestModel):
    name: str = Field(min_length=1, max_length=80)
