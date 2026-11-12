"""deliveries, verdicts, appeals, files, notifications, assistant, api keys

Revision ID: c8a41e0b77d2
Revises: b7c1e0a49d22
Create Date: 2026-11-04 02:10:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "c8a41e0b77d2"
down_revision: str | None = "b7c1e0a49d22"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = sa.CHAR(length=36)
TIMESTAMP = mysql.DATETIME(fsp=6)


def _fk(table: str, column: str, target: str) -> sa.ForeignKeyConstraint:
    referred = target.split(".")[0]
    return sa.ForeignKeyConstraint([column], [target], name=op.f(f"fk_{table}_{column}_{referred}"))


def upgrade() -> None:
    op.add_column("contracts", sa.Column("source_items", sa.JSON(), nullable=True))

    op.create_table(
        "files",
        sa.Column("id", UUID, nullable=False),
        sa.Column("org_id", UUID, nullable=False),
        sa.Column("uploaded_by", UUID, nullable=False),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("stored_name", sa.String(length=80), nullable=False),
        sa.Column("mime_type", sa.String(length=127), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.CHAR(length=64), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("created_at", TIMESTAMP, nullable=False),
        _fk("files", "org_id", "organizations.id"),
        _fk("files", "uploaded_by", "users.id"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_files")),
    )
    op.create_index(op.f("ix_files_org_id"), "files", ["org_id"])

    op.create_table(
        "deliveries",
        sa.Column("id", UUID, nullable=False),
        sa.Column("contract_id", UUID, nullable=False),
        sa.Column("submitted_by", UUID),
        sa.Column("a2a_task_id", sa.String(length=64)),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("file_ids", sa.JSON()),
        sa.Column("received_at", TIMESTAMP, nullable=False),
        sa.Column("is_late", sa.Boolean(), nullable=False),
        _fk("deliveries", "contract_id", "contracts.id"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_deliveries")),
    )
    op.create_index(op.f("ix_deliveries_contract_id"), "deliveries", ["contract_id", "received_at"])

    op.create_table(
        "verdicts",
        sa.Column("id", UUID, nullable=False),
        sa.Column("contract_id", UUID, nullable=False),
        sa.Column("delivery_id", UUID, nullable=False),
        sa.Column("result", sa.String(length=16), nullable=False),
        sa.Column("pass_ratio", sa.Numeric(7, 4), nullable=False),
        sa.Column("overall_score", sa.Numeric(5, 2), nullable=False),
        sa.Column("item_results", sa.JSON(), nullable=False),
        sa.Column("manipulation", sa.JSON()),
        sa.Column("reasoning", sa.Text(), nullable=False),
        sa.Column("judge_model", sa.String(length=120), nullable=False),
        sa.Column("second_opinion", sa.JSON()),
        sa.Column("prompt_version", sa.String(length=40), nullable=False),
        sa.Column("langsmith_run_id", sa.String(length=64)),
        sa.Column("created_at", TIMESTAMP, nullable=False),
        _fk("verdicts", "contract_id", "contracts.id"),
        _fk("verdicts", "delivery_id", "deliveries.id"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_verdicts")),
    )
    op.create_index(op.f("ix_verdicts_contract_id"), "verdicts", ["contract_id", "created_at"])

    op.create_table(
        "appeals",
        sa.Column("id", UUID, nullable=False),
        sa.Column("contract_id", UUID, nullable=False),
        sa.Column("verdict_id", UUID, nullable=False),
        sa.Column("argument", sa.Text(), nullable=False),
        sa.Column("memo", sa.JSON()),
        sa.Column("second_opinion", sa.JSON()),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("decided_by", UUID),
        sa.Column("decision_note", sa.String(length=500)),
        sa.Column("created_at", TIMESTAMP, nullable=False),
        sa.Column("decided_at", TIMESTAMP),
        _fk("appeals", "contract_id", "contracts.id"),
        _fk("appeals", "verdict_id", "verdicts.id"),
        _fk("appeals", "decided_by", "users.id"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_appeals")),
    )
    op.create_index(op.f("ix_appeals_contract_id"), "appeals", ["contract_id"])

    op.create_table(
        "notifications",
        sa.Column("id", UUID, nullable=False),
        sa.Column("org_id", UUID, nullable=False),
        sa.Column("user_id", UUID),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("body", sa.String(length=500), nullable=False),
        sa.Column("link", sa.String(length=255)),
        sa.Column("read_at", TIMESTAMP),
        sa.Column("created_at", TIMESTAMP, nullable=False),
        _fk("notifications", "org_id", "organizations.id"),
        _fk("notifications", "user_id", "users.id"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifications")),
    )
    op.create_index(op.f("ix_notifications_org_id"), "notifications", ["org_id", "created_at"])

    op.create_table(
        "agent_conversations",
        sa.Column("id", UUID, nullable=False),
        sa.Column("org_id", UUID, nullable=False),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("created_at", TIMESTAMP, nullable=False),
        _fk("agent_conversations", "org_id", "organizations.id"),
        _fk("agent_conversations", "user_id", "users.id"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_conversations")),
    )
    op.create_index(
        op.f("ix_agent_conversations_org_id"), "agent_conversations", ["org_id", "created_at"]
    )

    op.create_table(
        "agent_messages",
        sa.Column("id", UUID, nullable=False),
        sa.Column("conversation_id", UUID, nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tool_name", sa.String(length=64)),
        sa.Column("tool_payload", sa.JSON()),
        sa.Column("card", sa.JSON()),
        sa.Column("created_at", TIMESTAMP, nullable=False),
        _fk("agent_messages", "conversation_id", "agent_conversations.id"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_messages")),
    )
    op.create_index(
        op.f("ix_agent_messages_conversation_id"),
        "agent_messages",
        ["conversation_id", "created_at"],
    )

    op.create_table(
        "api_keys",
        sa.Column("id", UUID, nullable=False),
        sa.Column("org_id", UUID, nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("prefix", sa.String(length=16), nullable=False),
        sa.Column("key_hash", sa.CHAR(length=64), nullable=False),
        sa.Column("created_by", UUID, nullable=False),
        sa.Column("last_used_at", TIMESTAMP),
        sa.Column("revoked_at", TIMESTAMP),
        sa.Column("created_at", TIMESTAMP, nullable=False),
        _fk("api_keys", "org_id", "organizations.id"),
        _fk("api_keys", "created_by", "users.id"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_api_keys")),
        sa.UniqueConstraint("key_hash", name=op.f("uq_api_keys_key_hash")),
    )
    op.create_index(op.f("ix_api_keys_org_id"), "api_keys", ["org_id"])


def downgrade() -> None:
    op.drop_table("api_keys")
    op.drop_table("agent_messages")
    op.drop_table("agent_conversations")
    op.drop_table("notifications")
    op.drop_table("appeals")
    op.drop_table("verdicts")
    op.drop_table("deliveries")
    op.drop_table("files")
    op.drop_column("contracts", "source_items")
