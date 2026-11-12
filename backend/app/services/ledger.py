from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.state_machine import Ledger
from app.models import Contract, LedgerEntry
from app.services.contracts import Actor

ENTRY_TYPES = {
    Ledger.HELD: "escrow",
    Ledger.CAPTURED: "escrow",
    Ledger.RELEASED: "escrow",
    Ledger.FEE: "fee",
    Ledger.PAID_OUT: "payout",
}


def record(
    session: AsyncSession,
    *,
    org_id: str,
    contract: Contract,
    direction: Ledger,
    amount: Decimal,
    actor: Actor,
    paypal_reference: str | None,
    data: dict[str, Any] | None = None,
) -> None:
    """Append one ledger entry in the caller's transaction. Zero amounts aren't recorded."""
    if amount < 0:
        raise ValueError("Ledger amounts are never negative; the direction carries the sign")
    if amount == 0:
        return
    session.add(
        LedgerEntry(
            org_id=org_id,
            contract_id=contract.id,
            entry_type=ENTRY_TYPES[direction],
            direction=direction,
            amount=amount,
            currency=contract.currency,
            paypal_reference=paypal_reference,
            actor_type=actor.type,
            actor_id=actor.id,
            data=data,
        )
    )
