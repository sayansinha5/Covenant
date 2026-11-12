from datetime import datetime

from sqlalchemy import CHAR, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UtcDateTime, UuidPrimaryKey, utcnow


class PayPalFundingAccount(UuidPrimaryKey, Base):
    """The PayPal account an organization funds holds from. `vault_token_id` is a server-side
    credential for charging the payer and is never returned by the API."""

    __tablename__ = "paypal_funding_accounts"

    org_id: Mapped[str] = mapped_column(CHAR(36), ForeignKey("organizations.id"), index=True)
    mode: Mapped[str] = mapped_column(String(16))  # vault | approve_each
    paypal_customer_id: Mapped[str | None] = mapped_column(String(64))
    vault_token_id: Mapped[str | None] = mapped_column(String(64))
    payer_email: Mapped[str | None] = mapped_column(String(254))
    status: Mapped[str] = mapped_column(String(16))  # connected | disconnected
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow, onupdate=utcnow)


class PayPalVaultSession(UuidPrimaryKey, Base):
    """One "Connect PayPal" attempt. The random state travels through PayPal's redirect and is
    the only thing that links the unauthenticated return request to the organization."""

    __tablename__ = "paypal_vault_sessions"

    org_id: Mapped[str] = mapped_column(CHAR(36), ForeignKey("organizations.id"), index=True)
    user_id: Mapped[str] = mapped_column(CHAR(36), ForeignKey("users.id"))
    state_hash: Mapped[str] = mapped_column(CHAR(64), unique=True)
    setup_token_id: Mapped[str | None] = mapped_column(String(64))
    return_path: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16))  # pending | connected | cancelled | failed
    failure_reason: Mapped[str | None] = mapped_column(String(255))
    expires_at: Mapped[datetime] = mapped_column(UtcDateTime)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)
