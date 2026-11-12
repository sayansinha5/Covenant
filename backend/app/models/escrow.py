from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import CHAR, JSON, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Money, UtcDateTime, UuidPrimaryKey, utcnow


class Escrow(UuidPrimaryKey, Base):
    """The PayPal hold behind one contract.

    status: pending (reserved against the budget, hold being created) -> payer_action (approve
    each mode: waiting for the payer) -> held -> capture_pending | captured | voided; `failed`
    when PayPal declined the hold. `request_series` is the `n` in the PayPal-Request-Ids and
    only increases when a new hold is attempted after a definite failure."""

    __tablename__ = "escrows"
    __table_args__ = (
        Index(None, "org_id", "reserved_at"),
        Index(None, "status"),
        Index(None, "paypal_order_id"),
        Index(None, "paypal_authorization_id"),
    )

    contract_id: Mapped[str] = mapped_column(CHAR(36), ForeignKey("contracts.id"), unique=True)
    org_id: Mapped[str] = mapped_column(CHAR(36), ForeignKey("organizations.id"))
    status: Mapped[str] = mapped_column(String(16))
    request_series: Mapped[int] = mapped_column(Integer, default=1)
    amount: Mapped[Decimal] = mapped_column(Money)
    currency: Mapped[str] = mapped_column(CHAR(3))
    paypal_order_id: Mapped[str | None] = mapped_column(String(64))
    paypal_authorization_id: Mapped[str | None] = mapped_column(String(64))
    paypal_capture_id: Mapped[str | None] = mapped_column(String(64))
    payer_action_url: Mapped[str | None] = mapped_column(String(2048))
    amount_held: Mapped[Decimal] = mapped_column(Money, default=Decimal("0.00"))
    amount_captured: Mapped[Decimal] = mapped_column(Money, default=Decimal("0.00"))
    amount_released: Mapped[Decimal] = mapped_column(Money, default=Decimal("0.00"))
    # Planned by the settlement engine when the contract enters `settling`.
    settlement: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    failure_reason: Mapped[str | None] = mapped_column(String(500))
    # When the amount was last reserved against the budget: the month it counts in.
    reserved_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)
    auth_expires_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    honor_period_ends_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    # PayPal allows one reauthorization per authorization.
    reauthorized_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow, onupdate=utcnow)


class Payout(UuidPrimaryKey, Base):
    """Money sent to the provider after a capture. Its status is separate from the contract's,
    so a failed payout never reopens a settled contract."""

    __tablename__ = "payouts"
    __table_args__ = (Index(None, "provider_org_id", "created_at"),)

    contract_id: Mapped[str] = mapped_column(CHAR(36), ForeignKey("contracts.id"), unique=True)
    provider_org_id: Mapped[str] = mapped_column(CHAR(36), ForeignKey("organizations.id"))
    receiver_email: Mapped[str | None] = mapped_column(String(254))
    gross: Mapped[Decimal] = mapped_column(Money)
    fee: Mapped[Decimal] = mapped_column(Money)
    net: Mapped[Decimal] = mapped_column(Money)
    currency: Mapped[str] = mapped_column(CHAR(3))
    sender_batch_id: Mapped[str] = mapped_column(String(64), unique=True)
    paypal_batch_id: Mapped[str | None] = mapped_column(String(64))
    paypal_item_id: Mapped[str | None] = mapped_column(String(64))
    # pending | success | failed | unclaimed | returned
    status: Mapped[str] = mapped_column(String(16), default="pending")
    failure_reason: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow, onupdate=utcnow)


class IdempotencyKey(Base):
    """The stored response to a money request, replayed when the client retries with the same
    `Idempotency-Key`. Rows older than 24 hours are ignored and overwritten."""

    __tablename__ = "idempotency_keys"

    org_id: Mapped[str] = mapped_column(CHAR(36), primary_key=True)
    route: Mapped[str] = mapped_column(String(100), primary_key=True)
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    request_hash: Mapped[str] = mapped_column(CHAR(64))
    response_status: Mapped[int] = mapped_column(Integer)
    response_body: Mapped[Any] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)
