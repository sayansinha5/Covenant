from datetime import datetime

from sqlalchemy import CHAR, Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UtcDateTime, UuidPrimaryKey, utcnow


class User(UuidPrimaryKey, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(120))
    is_platform_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0)
    first_failed_login_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    locked_until: Mapped[datetime | None] = mapped_column(UtcDateTime)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)


class Organization(UuidPrimaryKey, Base):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(120))
    industry: Mapped[str] = mapped_column(String(40))
    country: Mapped[str] = mapped_column(CHAR(2))
    can_hire: Mapped[bool] = mapped_column(Boolean, default=False)
    can_provide: Mapped[bool] = mapped_column(Boolean, default=False)
    assistant_name: Mapped[str | None] = mapped_column(String(40))
    payout_email: Mapped[str | None] = mapped_column(String(254))
    # Set once the wizard finishes; later changes (e.g. disconnecting PayPal) don't reopen it.
    onboarded_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)


class Membership(UuidPrimaryKey, Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("user_id", "org_id"),)

    user_id: Mapped[str] = mapped_column(CHAR(36), ForeignKey("users.id"), index=True)
    org_id: Mapped[str] = mapped_column(CHAR(36), ForeignKey("organizations.id"), index=True)
    role: Mapped[str] = mapped_column(String(16))  # owner | admin | viewer
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)


class RefreshToken(UuidPrimaryKey, Base):
    """One row per issued refresh token. Tokens in a family descend from one login; presenting
    a token that was already rotated (replaced_by set) revokes the whole family."""

    __tablename__ = "refresh_tokens"

    user_id: Mapped[str] = mapped_column(CHAR(36), ForeignKey("users.id"), index=True)
    family_id: Mapped[str] = mapped_column(CHAR(36), index=True)
    token_hash: Mapped[str] = mapped_column(CHAR(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(UtcDateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    replaced_by: Mapped[str | None] = mapped_column(CHAR(36))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)
