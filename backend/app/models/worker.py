from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import CHAR, JSON, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Money, UtcDateTime, UuidPrimaryKey, utcnow


class Worker(UuidPrimaryKey, Base):
    """An agent (reached over A2A at `base_url`) or a human that a provider org offers for hire.
    Only `verified` workers appear in the marketplace."""

    __tablename__ = "workers"

    org_id: Mapped[str] = mapped_column(CHAR(36), ForeignKey("organizations.id"), index=True)
    kind: Mapped[str] = mapped_column(String(8))  # agent | human
    display_name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    base_url: Mapped[str | None] = mapped_column(String(255), unique=True)
    # The bearer token the runner sends to an agent. Hashed for the audit trail; the token
    # itself is kept because the runner has to present it, and no API response includes it.
    auth_token: Mapped[str | None] = mapped_column(String(255))
    auth_token_hash: Mapped[str | None] = mapped_column(CHAR(64))
    agent_card: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    categories: Mapped[list[str]] = mapped_column(JSON)
    price: Mapped[Decimal] = mapped_column(Money)
    currency: Mapped[str] = mapped_column(CHAR(3))
    # pending | verified | failed | suspended | unhealthy
    status: Mapped[str] = mapped_column(String(16), default="pending")
    reputation: Mapped[int] = mapped_column(Integer, default=50)
    jobs_completed: Mapped[int] = mapped_column(Integer, default=0)
    verified_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    suspended_reason: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow, onupdate=utcnow)


class WorkerVerification(UuidPrimaryKey, Base):
    """One step of a worker's verification run, shown live while the provider waits."""

    __tablename__ = "worker_verifications"

    worker_id: Mapped[str] = mapped_column(CHAR(36), ForeignKey("workers.id"), index=True)
    step: Mapped[str] = mapped_column(String(32))
    result: Mapped[str] = mapped_column(String(8))  # ok | failed
    detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)
