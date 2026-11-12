from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import CHAR, JSON, FetchedValue, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Money, UtcDateTime, UuidPrimaryKey, utcnow


class Contract(UuidPrimaryKey, Base):
    """An agreement to pay `amount` for work described by `spec`. `state` only changes through
    `app.services.contracts.transition`, which also writes the timeline event."""

    __tablename__ = "contracts"
    __table_args__ = (
        Index(None, "hirer_org_id", "state"),
        Index(None, "provider_org_id", "state"),
    )

    # AUTO_INCREMENT (from 1001) is set by the migration; the ORM only emits it for primary keys.
    number: Mapped[int] = mapped_column(Integer, unique=True, server_default=FetchedValue())
    hirer_org_id: Mapped[str] = mapped_column(CHAR(36), ForeignKey("organizations.id"))
    provider_org_id: Mapped[str] = mapped_column(CHAR(36), ForeignKey("organizations.id"))
    worker_id: Mapped[str] = mapped_column(CHAR(36), ForeignKey("workers.id"), index=True)
    mandate_id: Mapped[str | None] = mapped_column(CHAR(36), ForeignKey("mandates.id"))
    work_type: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(200))
    request_text: Mapped[str] = mapped_column(Text)
    input_file_id: Mapped[str | None] = mapped_column(CHAR(36))
    spec: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    spec_hash: Mapped[str | None] = mapped_column(CHAR(64))
    # Source rows the worker was given. Kept beside the spec so the spec hash stays the
    # acceptance spec only; the Arbiter aligns each delivered item with the row at the same index.
    source_items: Mapped[list[Any] | None] = mapped_column(JSON)
    amount: Mapped[Decimal] = mapped_column(Money)
    currency: Mapped[str] = mapped_column(CHAR(3))
    state: Mapped[str] = mapped_column(String(24))
    deadline_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    accept_by_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    appeal_window_ends_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    created_by_actor: Mapped[str] = mapped_column(String(16))
    version: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow, onupdate=utcnow)

    # `version` is bumped on every UPDATE and checked in its WHERE clause (optimistic locking).
    __mapper_args__: Mapping[str, Any] = {"version_id_col": version, "eager_defaults": True}


class ContractEvent(UuidPrimaryKey, Base):
    """The contract timeline. Append-only: one row per applied transition, plus notes that
    don't change state (`from_state == to_state`)."""

    __tablename__ = "contract_events"
    __table_args__ = (Index(None, "contract_id", "created_at"),)

    contract_id: Mapped[str] = mapped_column(CHAR(36), ForeignKey("contracts.id"))
    event: Mapped[str] = mapped_column(String(32))
    from_state: Mapped[str | None] = mapped_column(String(24))
    to_state: Mapped[str] = mapped_column(String(24))
    # user | buyer_agent | worker | paypal | system | api_key
    actor_type: Mapped[str] = mapped_column(String(16))
    actor_id: Mapped[str | None] = mapped_column(CHAR(36))
    message: Mapped[str] = mapped_column(String(500))
    data: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)


class Approval(UuidPrimaryKey, Base):
    """A request for an owner or admin to approve a contract above the approval threshold."""

    __tablename__ = "approvals"
    __table_args__ = (Index(None, "org_id", "status"),)

    contract_id: Mapped[str] = mapped_column(CHAR(36), ForeignKey("contracts.id"), index=True)
    org_id: Mapped[str] = mapped_column(CHAR(36), ForeignKey("organizations.id"))
    reason: Mapped[str] = mapped_column(String(500))
    # pending | approved | rejected | expired
    status: Mapped[str] = mapped_column(String(16), default="pending")
    decided_by: Mapped[str | None] = mapped_column(CHAR(36), ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    expires_at: Mapped[datetime] = mapped_column(UtcDateTime)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)
