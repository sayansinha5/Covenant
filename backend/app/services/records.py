"""Read models for the pages: contracts, the ledger, overview, notifications, earnings."""

import csv
import io
from decimal import Decimal
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.spec_writer.spec import fingerprint
from app.db.base import utcnow
from app.domain.policy import month_start
from app.models import (
    Appeal,
    Approval,
    Contract,
    ContractEvent,
    Delivery,
    Escrow,
    LedgerEntry,
    Notification,
    Organization,
    Payout,
    Verdict,
    Worker,
)
from app.services.contracts import ContractNotFound


async def list_contracts(
    session: AsyncSession, org_id: str, *, role: str | None, offset: int, limit: int
) -> tuple[list[dict[str, Any]], int]:
    condition = _role_filter(org_id, role)
    total = int(
        await session.scalar(select(func.count()).select_from(Contract).where(condition)) or 0
    )
    rows = (
        await session.execute(
            select(Contract, Worker.display_name)
            .join(Worker, Worker.id == Contract.worker_id)
            .where(condition)
            .order_by(Contract.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
    ).all()
    return [_summary(contract, name, org_id) for contract, name in rows], total


async def contract_detail(session: AsyncSession, org_id: str, contract_id: str) -> dict[str, Any]:
    contract = await session.get(Contract, contract_id)
    if contract is None or org_id not in (contract.hirer_org_id, contract.provider_org_id):
        raise ContractNotFound
    worker = await session.get(Worker, contract.worker_id)
    hirer = await session.get(Organization, contract.hirer_org_id)
    provider = await session.get(Organization, contract.provider_org_id)
    events = list(
        await session.scalars(
            select(ContractEvent)
            .where(ContractEvent.contract_id == contract.id)
            .order_by(ContractEvent.created_at)
        )
    )
    delivery = await session.scalar(
        select(Delivery)
        .where(Delivery.contract_id == contract.id)
        .order_by(Delivery.received_at.desc())
    )
    verdict = await session.scalar(
        select(Verdict)
        .where(Verdict.contract_id == contract.id)
        .order_by(Verdict.created_at.desc())
    )
    escrow = await session.scalar(select(Escrow).where(Escrow.contract_id == contract.id))
    appeal = await session.scalar(
        select(Appeal).where(Appeal.contract_id == contract.id).order_by(Appeal.created_at.desc())
    )
    spec_hash = contract.spec_hash or (fingerprint(contract.spec) if contract.spec else None)
    return {
        "contract": contract,
        "worker_name": worker.display_name if worker else "",
        "worker_kind": worker.kind if worker else "",
        "hirer_name": hirer.name if hirer else "",
        "provider_name": provider.name if provider else "",
        "role": _role(contract, org_id),
        "spec_fingerprint": spec_hash,
        "events": events,
        "delivery": delivery,
        "verdict": verdict,
        "escrow": escrow,
        "appeal": appeal,
    }


async def list_approvals(session: AsyncSession, org_id: str) -> list[Approval]:
    return list(
        await session.scalars(
            select(Approval)
            .where(Approval.org_id == org_id)
            .order_by(Approval.created_at.desc())
            .limit(100)
        )
    )


async def ledger_entries(
    session: AsyncSession, org_id: str, *, offset: int, limit: int
) -> tuple[list[LedgerEntry], int]:
    total = int(
        await session.scalar(
            select(func.count()).select_from(LedgerEntry).where(LedgerEntry.org_id == org_id)
        )
        or 0
    )
    rows = list(
        await session.scalars(
            select(LedgerEntry)
            .where(LedgerEntry.org_id == org_id)
            .order_by(LedgerEntry.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
    )
    return rows, total


async def ledger_page(
    session: AsyncSession, org_id: str, *, offset: int, limit: int
) -> tuple[list[dict[str, Any]], int]:
    """Ledger rows plus the contract number, so the grid can filter without a second round trip."""

    rows, total = await ledger_entries(session, org_id, offset=offset, limit=limit)
    if not rows:
        return [], total
    numbers = dict(
        (
            await session.execute(
                select(Contract.id, Contract.number).where(
                    Contract.id.in_([row.contract_id for row in rows])
                )
            )
        ).all()
    )
    return [
        {
            "id": row.id,
            "contract_id": row.contract_id,
            "contract_number": (
                f"C-{numbers[row.contract_id]}" if row.contract_id in numbers else None
            ),
            "direction": row.direction,
            "entry_type": row.entry_type,
            "amount": row.amount,
            "currency": row.currency,
            "paypal_reference": row.paypal_reference,
            "actor_type": row.actor_type,
            "created_at": row.created_at,
        }
        for row in rows
    ], total


async def ledger_csv(session: AsyncSession, org_id: str) -> str:
    rows, _ = await ledger_entries(session, org_id, offset=0, limit=5000)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["created_at", "contract_id", "direction", "entry_type", "amount", "currency"])
    for row in rows:
        writer.writerow(
            [
                row.created_at.isoformat(),
                row.contract_id,
                row.direction,
                row.entry_type,
                row.amount,
                row.currency,
            ]
        )
    return buffer.getvalue()


async def overview(session: AsyncSession, org_id: str) -> dict[str, Any]:
    states = dict(
        (
            await session.execute(
                select(Contract.state, func.count())
                .where(or_(Contract.hirer_org_id == org_id, Contract.provider_org_id == org_id))
                .group_by(Contract.state)
            )
        ).all()
    )
    captured = await session.scalar(
        select(func.coalesce(func.sum(LedgerEntry.amount), 0)).where(
            LedgerEntry.org_id == org_id,
            LedgerEntry.direction == "captured",
            LedgerEntry.created_at >= month_start(utcnow()),
        )
    )
    held = await session.scalar(
        select(func.coalesce(func.sum(Escrow.amount_held - Escrow.amount_captured), 0))
        .join(Contract, Contract.id == Escrow.contract_id)
        .where(Contract.hirer_org_id == org_id, Escrow.status == "held")
    )
    return {
        "by_state": {str(state): int(count) for state, count in states.items()},
        "captured_this_month": Decimal(captured or 0).quantize(Decimal("0.01")),
        "currently_held": Decimal(held or 0).quantize(Decimal("0.01")),
    }


async def notifications(session: AsyncSession, org_id: str) -> list[Notification]:
    return list(
        await session.scalars(
            select(Notification)
            .where(Notification.org_id == org_id)
            .order_by(Notification.created_at.desc())
            .limit(50)
        )
    )


async def mark_read(session: AsyncSession, org_id: str, notification_id: str | None) -> None:
    rows = await session.scalars(
        select(Notification).where(
            Notification.org_id == org_id,
            Notification.read_at.is_(None),
            *([Notification.id == notification_id] if notification_id else []),
        )
    )
    now = utcnow()
    for row in rows:
        row.read_at = now


async def earnings(session: AsyncSession, org_id: str) -> dict[str, Any]:
    payouts = list(
        await session.scalars(
            select(Payout)
            .where(Payout.provider_org_id == org_id)
            .order_by(Payout.created_at.desc())
            .limit(100)
        )
    )
    paid = sum((row.net for row in payouts if row.status == "success"), Decimal("0.00"))
    pending = sum((row.net for row in payouts if row.status == "pending"), Decimal("0.00"))
    return {"paid": paid, "pending": pending, "payouts": payouts}


def _role_filter(org_id: str, role: str | None) -> Any:
    if role == "hirer":
        return Contract.hirer_org_id == org_id
    if role == "provider":
        return Contract.provider_org_id == org_id
    return or_(Contract.hirer_org_id == org_id, Contract.provider_org_id == org_id)


def _role(contract: Contract, org_id: str) -> str:
    hirer = contract.hirer_org_id == org_id
    provider = contract.provider_org_id == org_id
    if hirer and provider:
        return "both"
    return "hirer" if hirer else "provider"


def _summary(contract: Contract, worker_name: str, org_id: str) -> dict[str, Any]:
    return {
        "id": contract.id,
        "number": f"C-{contract.number}",
        "title": contract.title,
        "state": contract.state,
        "amount": contract.amount,
        "currency": contract.currency,
        "worker_name": worker_name,
        "role": _role(contract, org_id),
        "updated_at": contract.updated_at,
    }
