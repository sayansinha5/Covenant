from datetime import datetime
from typing import Any

from sqlalchemy import CHAR, JSON, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UtcDateTime, UuidPrimaryKey, utcnow


class PayPalOperation(UuidPrimaryKey, Base):
    """Audit row per mutating PayPal call, keyed by its PayPal-Request-Id. A retry with the
    same request ID updates the row (latest response, attempt count) instead of adding one."""

    __tablename__ = "paypal_operations"

    contract_id: Mapped[str | None] = mapped_column(CHAR(36), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    request_id: Mapped[str] = mapped_column(String(108), unique=True)
    http_method: Mapped[str] = mapped_column(String(8))
    path: Mapped[str] = mapped_column(String(255))
    request_body: Mapped[Any | None] = mapped_column(JSON)
    response_status: Mapped[int | None] = mapped_column(Integer)
    response_body: Mapped[Any | None] = mapped_column(JSON)
    paypal_debug_id: Mapped[str | None] = mapped_column(String(64))
    attempts: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow, onupdate=utcnow)
