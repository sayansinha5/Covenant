from datetime import datetime
from decimal import Decimal

from sqlalchemy import CHAR, JSON, Boolean, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Money, UtcDateTime, UuidPrimaryKey, utcnow


class Mandate(UuidPrimaryKey, Base):
    """A signed version of an organization's spending rules. Rows are never edited: signing a
    new version inserts a row and switches `is_active`; contracts keep the version they used."""

    __tablename__ = "mandates"
    __table_args__ = (UniqueConstraint("org_id", "version"),)

    org_id: Mapped[str] = mapped_column(CHAR(36), ForeignKey("organizations.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    monthly_budget: Mapped[Decimal] = mapped_column(Money)
    per_task_cap: Mapped[Decimal] = mapped_column(Money)
    approval_threshold: Mapped[Decimal] = mapped_column(Money)
    currency: Mapped[str] = mapped_column(CHAR(3))
    allowed_work_types: Mapped[list[str]] = mapped_column(JSON)
    signed_by: Mapped[str] = mapped_column(CHAR(36), ForeignKey("users.id"))
    signed_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
