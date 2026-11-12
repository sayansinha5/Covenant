"""The mandate policy engine. Pure: no I/O, no clock, no LLM. Every hold passes through
`evaluate`, whether the buyer agent, a person in the web app or an MCP client asked for it."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal

WorkType = Literal["translation", "catalog_data", "copywriting", "design"]
WORK_TYPES: tuple[WorkType, ...] = ("translation", "catalog_data", "copywriting", "design")
WORK_TYPE_LABELS: dict[str, str] = {
    "translation": "translation",
    "catalog_data": "catalogue data",
    "copywriting": "copywriting",
    "design": "design",
}


class Outcome(StrEnum):
    ALLOWED = "allowed"
    NEEDS_APPROVAL = "needs_approval"
    REJECTED = "rejected"


@dataclass(frozen=True)
class MandateTerms:
    version: int
    monthly_budget: Decimal
    per_task_cap: Decimal
    approval_threshold: Decimal
    allowed_work_types: frozenset[str]
    is_active: bool = True


@dataclass(frozen=True)
class PolicyDecision:
    outcome: Outcome
    code: str
    reason: str
    mandate_version: int | None = None

    @property
    def allowed(self) -> bool:
        return self.outcome is Outcome.ALLOWED


def usd(amount: Decimal) -> str:
    """$40 for whole dollars, $40.50 otherwise (reasons are read by people and the agent)."""
    return f"${amount:,.0f}" if amount == amount.to_integral_value() else f"${amount:,.2f}"


def month_start(moment: datetime) -> datetime:
    """Start of the calendar month (UTC) that budget checks count spend from."""
    return moment.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def evaluate(
    mandate: MandateTerms | None,
    *,
    amount: Decimal,
    work_type: str,
    committed_this_month: Decimal,
    funding_connected: bool,
    approved: bool = False,
) -> PolicyDecision:
    """Run the six checks in order; the first that fails decides. `committed_this_month` is
    held + captured for contracts funded this month, excluding the one being checked.
    `approved` is True once an owner or admin approved this contract's spend."""
    if amount <= 0:
        raise ValueError("amount must be positive")

    if mandate is None or not mandate.is_active:
        return PolicyDecision(
            Outcome.REJECTED,
            "MANDATE_MISSING",
            "There's no signed mandate. An owner needs to sign one before anything is funded.",
        )
    version = mandate.version

    def reject(code: str, reason: str) -> PolicyDecision:
        return PolicyDecision(Outcome.REJECTED, code, reason, version)

    if work_type not in mandate.allowed_work_types:
        label = WORK_TYPE_LABELS.get(work_type, work_type)
        return reject("MANDATE_WORK_TYPE", f"Your mandate doesn't allow {label} work.")
    if amount > mandate.per_task_cap:
        return reject(
            "MANDATE_OVER_TASK_CAP",
            f"This contract is {usd(amount)}. Your mandate allows at most "
            f"{usd(mandate.per_task_cap)} per task.",
        )
    remaining = mandate.monthly_budget - committed_this_month
    if amount > remaining:
        return reject(
            "MANDATE_OVER_BUDGET",
            f"This contract is {usd(amount)} but only {usd(max(remaining, Decimal(0)))} of "
            f"your {usd(mandate.monthly_budget)} monthly budget is left.",
        )
    if amount > mandate.approval_threshold and not approved:
        return PolicyDecision(
            Outcome.NEEDS_APPROVAL,
            "APPROVAL_REQUIRED",
            f"This contract is {usd(amount)}. Your mandate asks for approval above "
            f"{usd(mandate.approval_threshold)}.",
            version,
        )
    if not funding_connected:
        return reject(
            "FUNDING_NOT_CONNECTED",
            "No PayPal account is connected. Connect PayPal in Settings to fund contracts.",
        )
    return PolicyDecision(Outcome.ALLOWED, "WITHIN_MANDATE", "Within your mandate.", version)
