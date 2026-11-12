from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UtcDateTime, UuidPrimaryKey, utcnow


class OutboxJob(UuidPrimaryKey, Base):
    """Work to do outside the database (PayPal, workers, the LLM), written in the same
    transaction as the state change that needs it and executed by the runner.

    status: queued -> running -> done; a retryable failure goes back to queued with a later
    `run_after`; a permanent failure is `failed`; running out of attempts is `dead`."""

    __tablename__ = "outbox_jobs"
    __table_args__ = (Index(None, "status", "run_after"),)

    kind: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    dedupe_key: Mapped[str] = mapped_column(String(191), unique=True)
    status: Mapped[str] = mapped_column(String(16), default="queued")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer)
    run_after: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)
    locked_until: Mapped[datetime | None] = mapped_column(UtcDateTime)
    locked_by: Mapped[str | None] = mapped_column(String(64))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow, onupdate=utcnow)
