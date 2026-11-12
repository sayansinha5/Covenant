"""core domain: workers, contracts, timeline, approvals, ledger, outbox

Revision ID: 4135e91b105c
Revises: 1e7d54ba5366
Create Date: 2026-11-03 15:54:13.639748
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "4135e91b105c"
down_revision: str | None = "1e7d54ba5366"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MONEY = sa.Numeric(precision=12, scale=2)
UUID = sa.CHAR(length=36)
TIMESTAMP = mysql.DATETIME(fsp=6)
CONTRACT_NUMBER_START = 1001


def _fk(table: str, column: str, target: str) -> sa.ForeignKeyConstraint:
    referred = target.split(".")[0]
    return sa.ForeignKeyConstraint([column], [target], name=op.f(f"fk_{table}_{column}_{referred}"))


def upgrade() -> None:
    op.create_table(
        "outbox_jobs",
        sa.Column("id", UUID, nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("dedupe_key", sa.String(length=191), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("run_after", TIMESTAMP, nullable=False),
        sa.Column("locked_until", TIMESTAMP),
        sa.Column("locked_by", sa.String(length=64)),
        sa.Column("last_error", sa.Text()),
        sa.Column("created_at", TIMESTAMP, nullable=False),
        sa.Column("updated_at", TIMESTAMP, nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_outbox_jobs")),
        sa.UniqueConstraint("dedupe_key", name=op.f("uq_outbox_jobs_dedupe_key")),
    )
    op.create_index(op.f("ix_outbox_jobs_status_run_after"), "outbox_jobs", ["status", "run_after"])

    op.create_table(
        "workers",
        sa.Column("id", UUID, nullable=False),
        sa.Column("org_id", UUID, nullable=False),
        sa.Column("kind", sa.String(length=8), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("base_url", sa.String(length=255)),
        sa.Column("agent_card", sa.JSON()),
        sa.Column("categories", sa.JSON(), nullable=False),
        sa.Column("price", MONEY, nullable=False),
        sa.Column("currency", sa.CHAR(length=3), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("reputation", sa.Integer(), nullable=False),
        sa.Column("jobs_completed", sa.Integer(), nullable=False),
        sa.Column("verified_at", TIMESTAMP),
        sa.Column("suspended_reason", sa.String(length=255)),
        sa.Column("created_at", TIMESTAMP, nullable=False),
        sa.Column("updated_at", TIMESTAMP, nullable=False),
        _fk("workers", "org_id", "organizations.id"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workers")),
        sa.UniqueConstraint("base_url", name=op.f("uq_workers_base_url")),
    )
    op.create_index(op.f("ix_workers_org_id"), "workers", ["org_id"])

    op.create_table(
        "worker_verifications",
        sa.Column("id", UUID, nullable=False),
        sa.Column("worker_id", UUID, nullable=False),
        sa.Column("step", sa.String(length=32), nullable=False),
        sa.Column("result", sa.String(length=8), nullable=False),
        sa.Column("detail", sa.Text()),
        sa.Column("created_at", TIMESTAMP, nullable=False),
        _fk("worker_verifications", "worker_id", "workers.id"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_worker_verifications")),
    )
    op.create_index(
        op.f("ix_worker_verifications_worker_id"), "worker_verifications", ["worker_id"]
    )

    op.create_table(
        "contracts",
        sa.Column("id", UUID, nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("hirer_org_id", UUID, nullable=False),
        sa.Column("provider_org_id", UUID, nullable=False),
        sa.Column("worker_id", UUID, nullable=False),
        sa.Column("mandate_id", UUID),
        sa.Column("work_type", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("request_text", sa.Text(), nullable=False),
        sa.Column("input_file_id", UUID),
        sa.Column("spec", sa.JSON()),
        sa.Column("spec_hash", sa.CHAR(length=64)),
        sa.Column("amount", MONEY, nullable=False),
        sa.Column("currency", sa.CHAR(length=3), nullable=False),
        sa.Column("state", sa.String(length=24), nullable=False),
        sa.Column("deadline_at", TIMESTAMP),
        sa.Column("accept_by_at", TIMESTAMP),
        sa.Column("appeal_window_ends_at", TIMESTAMP),
        sa.Column("created_by_actor", sa.String(length=16), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", TIMESTAMP, nullable=False),
        sa.Column("updated_at", TIMESTAMP, nullable=False),
        _fk("contracts", "hirer_org_id", "organizations.id"),
        _fk("contracts", "provider_org_id", "organizations.id"),
        _fk("contracts", "worker_id", "workers.id"),
        _fk("contracts", "mandate_id", "mandates.id"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_contracts")),
        sa.UniqueConstraint("number", name=op.f("uq_contracts_number")),
    )
    # Human contract numbers (C-1001, …). SQLAlchemy only emits AUTO_INCREMENT on primary keys;
    # InnoDB allows it on any column that leads an index, here the unique key above.
    op.execute(
        "ALTER TABLE contracts MODIFY number INT NOT NULL AUTO_INCREMENT, "
        f"AUTO_INCREMENT = {CONTRACT_NUMBER_START}"
    )
    op.create_index(op.f("ix_contracts_hirer_org_id_state"), "contracts", ["hirer_org_id", "state"])
    op.create_index(
        op.f("ix_contracts_provider_org_id_state"), "contracts", ["provider_org_id", "state"]
    )
    op.create_index(op.f("ix_contracts_worker_id"), "contracts", ["worker_id"])

    op.create_table(
        "contract_events",
        sa.Column("id", UUID, nullable=False),
        sa.Column("contract_id", UUID, nullable=False),
        sa.Column("event", sa.String(length=32), nullable=False),
        sa.Column("from_state", sa.String(length=24)),
        sa.Column("to_state", sa.String(length=24), nullable=False),
        sa.Column("actor_type", sa.String(length=16), nullable=False),
        sa.Column("actor_id", UUID),
        sa.Column("message", sa.String(length=500), nullable=False),
        sa.Column("data", sa.JSON()),
        sa.Column("created_at", TIMESTAMP, nullable=False),
        _fk("contract_events", "contract_id", "contracts.id"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_contract_events")),
    )
    op.create_index(
        op.f("ix_contract_events_contract_id_created_at"),
        "contract_events",
        ["contract_id", "created_at"],
    )

    op.create_table(
        "approvals",
        sa.Column("id", UUID, nullable=False),
        sa.Column("contract_id", UUID, nullable=False),
        sa.Column("org_id", UUID, nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("decided_by", UUID),
        sa.Column("decided_at", TIMESTAMP),
        sa.Column("expires_at", TIMESTAMP, nullable=False),
        sa.Column("created_at", TIMESTAMP, nullable=False),
        _fk("approvals", "contract_id", "contracts.id"),
        _fk("approvals", "org_id", "organizations.id"),
        _fk("approvals", "decided_by", "users.id"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_approvals")),
    )
    op.create_index(op.f("ix_approvals_contract_id"), "approvals", ["contract_id"])
    op.create_index(op.f("ix_approvals_org_id_status"), "approvals", ["org_id", "status"])

    op.create_table(
        "ledger_entries",
        sa.Column("id", UUID, nullable=False),
        sa.Column("org_id", UUID, nullable=False),
        sa.Column("contract_id", UUID, nullable=False),
        sa.Column("entry_type", sa.String(length=16), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("amount", MONEY, nullable=False),
        sa.Column("currency", sa.CHAR(length=3), nullable=False),
        sa.Column("paypal_reference", sa.String(length=64)),
        sa.Column("actor_type", sa.String(length=16), nullable=False),
        sa.Column("actor_id", UUID),
        sa.Column("data", sa.JSON()),
        sa.Column("created_at", TIMESTAMP, nullable=False),
        _fk("ledger_entries", "org_id", "organizations.id"),
        _fk("ledger_entries", "contract_id", "contracts.id"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ledger_entries")),
    )
    op.create_index(op.f("ix_ledger_entries_contract_id"), "ledger_entries", ["contract_id"])
    op.create_index(
        op.f("ix_ledger_entries_org_id_created_at"), "ledger_entries", ["org_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_table("ledger_entries")
    op.drop_table("approvals")
    op.drop_table("contract_events")
    op.drop_table("contracts")
    op.drop_table("worker_verifications")
    op.drop_table("workers")
    op.drop_table("outbox_jobs")
