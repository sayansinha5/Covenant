"""webhooks and reconciliation: webhook_events, reconciliation_runs

Revision ID: db910f998626
Revises: 20e5fbfce786
Create Date: 2026-11-03 16:51:26.817353
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "db910f998626"
down_revision: str | None = "20e5fbfce786"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = sa.CHAR(length=36)
TIMESTAMP = mysql.DATETIME(fsp=6)


def _fk(table: str, column: str, target: str) -> sa.ForeignKeyConstraint:
    referred = target.split(".")[0]
    return sa.ForeignKeyConstraint([column], [target], name=op.f(f"fk_{table}_{column}_{referred}"))


def upgrade() -> None:
    op.create_table(
        "webhook_events",
        sa.Column("id", UUID, nullable=False),
        sa.Column("paypal_event_id", sa.String(length=64)),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("resource_id", sa.String(length=64)),
        sa.Column("verified", sa.Boolean(), nullable=False),
        sa.Column("processed", sa.Boolean(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("contract_id", UUID),
        sa.Column("result", sa.String(length=16)),
        sa.Column("outcome", sa.String(length=500)),
        sa.Column("error", sa.Text()),
        sa.Column("received_at", TIMESTAMP, nullable=False),
        sa.Column("processed_at", TIMESTAMP),
        _fk("webhook_events", "contract_id", "contracts.id"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_webhook_events")),
        sa.UniqueConstraint("paypal_event_id", name=op.f("uq_webhook_events_paypal_event_id")),
    )
    op.create_index(op.f("ix_webhook_events_received_at"), "webhook_events", ["received_at"])

    op.create_table(
        "reconciliation_runs",
        sa.Column("id", UUID, nullable=False),
        sa.Column("trigger", sa.String(length=16), nullable=False),
        sa.Column("requested_by", UUID),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("checked", sa.Integer(), nullable=False),
        sa.Column("in_sync", sa.Integer(), nullable=False),
        sa.Column("fixed", sa.Integer(), nullable=False),
        sa.Column("needs_attention", sa.Integer(), nullable=False),
        sa.Column("errors", sa.Integer(), nullable=False),
        sa.Column("findings", sa.JSON(), nullable=False),
        sa.Column("started_at", TIMESTAMP),
        sa.Column("finished_at", TIMESTAMP),
        sa.Column("created_at", TIMESTAMP, nullable=False),
        _fk("reconciliation_runs", "requested_by", "users.id"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reconciliation_runs")),
    )
    op.create_index(
        op.f("ix_reconciliation_runs_created_at"), "reconciliation_runs", ["created_at"]
    )


def downgrade() -> None:
    op.drop_table("reconciliation_runs")
    op.drop_table("webhook_events")
