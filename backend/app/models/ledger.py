from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import CHAR, JSON, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Money, UtcDateTime, UuidPrimaryKey, utcnow


class LedgerEntry(UuidPrimaryKey, Base):
    """Append-only record of money movement, from the point of view of `org_id`. The app's
    database user can only INSERT and SELECT here; corrections are new entries.

    `entry_type` names the account the movement belongs to (`escrow`, `fee`, `payout`);
    `direction` is the movement itself (`held`, `captured`, `released`, `fee`, `paid_out`)."""

    __tablename__ = "ledger_entries"
    __table_args__ = (Index(None, "org_id", "created_at"),)

    org_id: Mapped[str] = mapped_column(CHAR(36), ForeignKey("organizations.id"))
    contract_id: Mapped[str] = mapped_column(CHAR(36), ForeignKey("contracts.id"), index=True)
    entry_type: Mapped[str] = mapped_column(String(16))
    direction: Mapped[str] = mapped_column(String(16))
    amount: Mapped[Decimal] = mapped_column(Money)
    currency: Mapped[str] = mapped_column(CHAR(3))
    paypal_reference: Mapped[str | None] = mapped_column(String(64))
    actor_type: Mapped[str] = mapped_column(String(16))
    actor_id: Mapped[str | None] = mapped_column(CHAR(36))
    data: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)
