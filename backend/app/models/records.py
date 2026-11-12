"""Deliveries, verdicts, appeals, files, notifications, assistant history and API keys."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import CHAR, JSON, Boolean, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UtcDateTime, UuidPrimaryKey, utcnow


class StoredFile(UuidPrimaryKey, Base):
    __tablename__ = "files"

    org_id: Mapped[str] = mapped_column(CHAR(36), ForeignKey("organizations.id"), index=True)
    uploaded_by: Mapped[str] = mapped_column(CHAR(36), ForeignKey("users.id"))
    original_name: Mapped[str] = mapped_column(String(255))
    stored_name: Mapped[str] = mapped_column(String(80))
    mime_type: Mapped[str] = mapped_column(String(127))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(CHAR(64))
    purpose: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)


class Delivery(UuidPrimaryKey, Base):
    """One submitted delivery. `content` is untrusted and is never rendered as HTML."""

    __tablename__ = "deliveries"
    __table_args__ = (Index(None, "contract_id", "received_at"),)

    contract_id: Mapped[str] = mapped_column(CHAR(36), ForeignKey("contracts.id"))
    submitted_by: Mapped[str | None] = mapped_column(CHAR(36))
    a2a_task_id: Mapped[str | None] = mapped_column(String(64))
    content: Mapped[Any] = mapped_column(JSON)
    file_ids: Mapped[list[str] | None] = mapped_column(JSON)
    received_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)
    is_late: Mapped[bool] = mapped_column(Boolean, default=False)


class Verdict(UuidPrimaryKey, Base):
    __tablename__ = "verdicts"
    __table_args__ = (Index(None, "contract_id", "created_at"),)

    contract_id: Mapped[str] = mapped_column(CHAR(36), ForeignKey("contracts.id"))
    delivery_id: Mapped[str] = mapped_column(CHAR(36), ForeignKey("deliveries.id"))
    result: Mapped[str] = mapped_column(String(16))
    pass_ratio: Mapped[Decimal] = mapped_column(Numeric(7, 4))
    overall_score: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    item_results: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    manipulation: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    reasoning: Mapped[str] = mapped_column(Text)
    judge_model: Mapped[str] = mapped_column(String(120), default="")
    second_opinion: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    prompt_version: Mapped[str] = mapped_column(String(40))
    langsmith_run_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)


class Appeal(UuidPrimaryKey, Base):
    __tablename__ = "appeals"

    contract_id: Mapped[str] = mapped_column(CHAR(36), ForeignKey("contracts.id"), index=True)
    verdict_id: Mapped[str] = mapped_column(CHAR(36), ForeignKey("verdicts.id"))
    argument: Mapped[str] = mapped_column(Text)
    memo: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    second_opinion: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16), default="open")
    decided_by: Mapped[str | None] = mapped_column(CHAR(36), ForeignKey("users.id"))
    decision_note: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(UtcDateTime)


class Notification(UuidPrimaryKey, Base):
    __tablename__ = "notifications"
    __table_args__ = (Index(None, "org_id", "created_at"),)

    org_id: Mapped[str] = mapped_column(CHAR(36), ForeignKey("organizations.id"))
    user_id: Mapped[str | None] = mapped_column(CHAR(36), ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(160))
    body: Mapped[str] = mapped_column(String(500))
    link: Mapped[str | None] = mapped_column(String(255))
    read_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)


class AgentConversation(UuidPrimaryKey, Base):
    __tablename__ = "agent_conversations"
    __table_args__ = (Index(None, "org_id", "created_at"),)

    org_id: Mapped[str] = mapped_column(CHAR(36), ForeignKey("organizations.id"))
    user_id: Mapped[str] = mapped_column(CHAR(36), ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(120), default="New conversation")
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)


class AgentMessage(UuidPrimaryKey, Base):
    __tablename__ = "agent_messages"
    __table_args__ = (Index(None, "conversation_id", "created_at"),)

    conversation_id: Mapped[str] = mapped_column(CHAR(36), ForeignKey("agent_conversations.id"))
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    tool_name: Mapped[str | None] = mapped_column(String(64))
    tool_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    card: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)


class ApiKey(UuidPrimaryKey, Base):
    """Only the SHA-256 of the key is stored. `prefix` is the non-secret start shown in Settings."""

    __tablename__ = "api_keys"

    org_id: Mapped[str] = mapped_column(CHAR(36), ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    prefix: Mapped[str] = mapped_column(String(16))
    key_hash: Mapped[str] = mapped_column(CHAR(64), unique=True)
    created_by: Mapped[str] = mapped_column(CHAR(36), ForeignKey("users.id"))
    last_used_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)
