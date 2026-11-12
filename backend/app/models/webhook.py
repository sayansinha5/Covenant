from datetime import datetime
from typing import Any

from sqlalchemy import CHAR, JSON, Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UtcDateTime, UuidPrimaryKey, utcnow


class WebhookEvent(UuidPrimaryKey, Base):
    """One PayPal webhook delivery. Verified events are unique by PayPal's event ID, so a
    redelivery is recognised and dropped. Rejected deliveries are logged with only the claimed
    ID and type (`paypal_event_id` stays NULL): their payload is untrusted and isn't kept."""

    __tablename__ = "webhook_events"
    __table_args__ = (Index(None, "received_at"),)

    paypal_event_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    event_type: Mapped[str] = mapped_column(String(64))
    resource_id: Mapped[str | None] = mapped_column(String(64))
    verified: Mapped[bool] = mapped_column(Boolean)
    processed: Mapped[bool] = mapped_column(Boolean, default=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    contract_id: Mapped[str | None] = mapped_column(CHAR(36), ForeignKey("contracts.id"))
    # in_sync | fixed | needs_attention | ignored, and what processing did.
    result: Mapped[str | None] = mapped_column(String(16))
    outcome: Mapped[str | None] = mapped_column(String(500))
    error: Mapped[str | None] = mapped_column(Text)
    received_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(UtcDateTime)


class ReconciliationRun(UuidPrimaryKey, Base):
    """One pass comparing open contracts and recent payouts with PayPal (S17 shows the last)."""

    __tablename__ = "reconciliation_runs"
    __table_args__ = (Index(None, "created_at"),)

    trigger: Mapped[str] = mapped_column(String(16))  # schedule | admin
    requested_by: Mapped[str | None] = mapped_column(CHAR(36), ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(16), default="queued")  # queued|running|done|failed
    checked: Mapped[int] = mapped_column(Integer, default=0)
    in_sync: Mapped[int] = mapped_column(Integer, default=0)
    fixed: Mapped[int] = mapped_column(Integer, default=0)
    needs_attention: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[int] = mapped_column(Integer, default=0)
    # Fixed, needs-attention and error findings: {contract_id, contract_number, result, message}.
    findings: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    started_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    finished_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)
