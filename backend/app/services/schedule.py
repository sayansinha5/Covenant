"""Load the contracts and holds the settlement calendar draws."""

from dataclasses import asdict
from datetime import timedelta

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.base import utcnow
from app.domain.schedule import ScheduleContract, build_schedule
from app.models import Contract, Escrow, Worker


async def settlement_schedule(
    session: AsyncSession, settings: Settings, org_id: str
) -> dict[str, object]:
    rows = (
        await session.execute(
            select(Contract, Worker.display_name, Escrow)
            .join(Worker, Worker.id == Contract.worker_id)
            .outerjoin(Escrow, Escrow.contract_id == Contract.id)
            .where(or_(Contract.hirer_org_id == org_id, Contract.provider_org_id == org_id))
            .order_by(Contract.updated_at.desc())
            .limit(80)
        )
    ).all()
    contracts = [
        ScheduleContract(
            contract_id=contract.id,
            number=f"C-{contract.number}",
            title=contract.title,
            state=contract.state,
            worker_name=worker_name,
            created_at=contract.created_at,
            accept_by_at=contract.accept_by_at,
            deadline_at=contract.deadline_at,
            appeal_window_ends_at=contract.appeal_window_ends_at,
            honor_period_ends_at=escrow.honor_period_ends_at if escrow is not None else None,
            auth_expires_at=escrow.auth_expires_at if escrow is not None else None,
        )
        for contract, worker_name, escrow in rows
    ]
    resources, windows = build_schedule(
        contracts, appeal_window=timedelta(minutes=float(settings.appeal_window_minutes))
    )
    return {
        "generated_at": utcnow(),
        "resources": [asdict(resource) for resource in resources],
        "events": [asdict(window) for window in windows],
    }
