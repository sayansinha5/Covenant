"""Settlement windows for one contract.

Dates come from the contract and its PayPal hold. No clock and no database.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

_MINIMUM = timedelta(minutes=15)
_REAUTHORIZE = timedelta(hours=2)


@dataclass(frozen=True, slots=True)
class ScheduleContract:
    contract_id: str
    number: str
    title: str
    state: str
    worker_name: str
    created_at: datetime
    accept_by_at: datetime | None
    deadline_at: datetime | None
    appeal_window_ends_at: datetime | None
    honor_period_ends_at: datetime | None
    auth_expires_at: datetime | None


@dataclass(frozen=True, slots=True)
class ScheduleResource:
    id: str
    name: str
    state: str
    worker_name: str


@dataclass(frozen=True, slots=True)
class ScheduleWindow:
    id: str
    resource_id: str
    name: str
    kind: str
    start: datetime
    end: datetime
    contract_id: str


def build_schedule(
    contracts: list[ScheduleContract], *, appeal_window: timedelta
) -> tuple[list[ScheduleResource], list[ScheduleWindow]]:
    resources: list[ScheduleResource] = []
    windows: list[ScheduleWindow] = []
    for contract in contracts:
        rows = _windows(contract, appeal_window=appeal_window)
        if not rows:
            continue
        resources.append(
            ScheduleResource(
                id=contract.contract_id,
                name=_resource_name(contract),
                state=contract.state,
                worker_name=contract.worker_name,
            )
        )
        windows.extend(rows)
    windows.sort(key=lambda window: window.start)
    return resources, windows


def _windows(contract: ScheduleContract, *, appeal_window: timedelta) -> list[ScheduleWindow]:
    rows: list[ScheduleWindow] = []
    if contract.accept_by_at is not None:
        rows.append(_window(contract, "accept", "Worker must accept", None, contract.accept_by_at))
    if contract.deadline_at is not None:
        rows.append(
            _window(contract, "delivery", "Work is due", contract.created_at, contract.deadline_at)
        )
    if contract.appeal_window_ends_at is not None:
        rows.append(
            _window(
                contract,
                "appeal",
                "Appeal is open",
                contract.appeal_window_ends_at - appeal_window,
                contract.appeal_window_ends_at,
            )
        )
    if contract.honor_period_ends_at is not None:
        rows.append(
            _window(
                contract,
                "honor",
                "PayPal is holding the funds",
                contract.created_at,
                contract.honor_period_ends_at,
            )
        )
    expires = contract.auth_expires_at
    if expires is not None and _needs_renewal(contract.honor_period_ends_at, expires):
        rows.append(
            _window(
                contract,
                "reauthorize",
                "Authorization needs renewal",
                expires - _REAUTHORIZE,
                expires,
            )
        )
    return rows


def _needs_renewal(honor: datetime | None, expires: datetime) -> bool:
    if honor is None:
        return True
    return expires + timedelta(hours=1) < honor


def _window(
    contract: ScheduleContract,
    kind: str,
    name: str,
    start: datetime | None,
    end: datetime,
) -> ScheduleWindow:
    begin = start if start is not None and start < end else end - _REAUTHORIZE
    if end - begin < _MINIMUM:
        begin = end - _MINIMUM
    return ScheduleWindow(
        id=f"{contract.contract_id}:{kind}",
        resource_id=contract.contract_id,
        name=name,
        kind=kind,
        start=begin,
        end=end,
        contract_id=contract.contract_id,
    )


def _resource_name(contract: ScheduleContract) -> str:
    title = contract.title if len(contract.title) <= 42 else f"{contract.title[:41]}…"
    return f"{contract.number} · {contract.worker_name} — {title}"
