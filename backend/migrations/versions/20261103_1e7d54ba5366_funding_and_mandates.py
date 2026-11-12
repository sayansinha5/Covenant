"""funding and mandates: paypal funding accounts, vault sessions, mandates

Revision ID: 1e7d54ba5366
Revises: 81d9aefa9afd
Create Date: 2026-11-03 15:23:38.036200
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "1e7d54ba5366"
down_revision: str | None = "81d9aefa9afd"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MONEY = sa.Numeric(precision=12, scale=2)


def upgrade() -> None:
    op.add_column("organizations", sa.Column("onboarded_at", mysql.DATETIME(fsp=6)))
    op.create_table(
        "mandates",
        sa.Column("id", sa.CHAR(length=36), nullable=False),
        sa.Column("org_id", sa.CHAR(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("monthly_budget", MONEY, nullable=False),
        sa.Column("per_task_cap", MONEY, nullable=False),
        sa.Column("approval_threshold", MONEY, nullable=False),
        sa.Column("currency", sa.CHAR(length=3), nullable=False),
        sa.Column("allowed_work_types", sa.JSON(), nullable=False),
        sa.Column("signed_by", sa.CHAR(length=36), nullable=False),
        sa.Column("signed_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["org_id"], ["organizations.id"], name=op.f("fk_mandates_org_id_organizations")
        ),
        sa.ForeignKeyConstraint(
            ["signed_by"], ["users.id"], name=op.f("fk_mandates_signed_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mandates")),
        sa.UniqueConstraint("org_id", "version", name=op.f("uq_mandates_org_id_version")),
    )
    op.create_index(op.f("ix_mandates_org_id"), "mandates", ["org_id"])
    op.create_table(
        "paypal_funding_accounts",
        sa.Column("id", sa.CHAR(length=36), nullable=False),
        sa.Column("org_id", sa.CHAR(length=36), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("paypal_customer_id", sa.String(length=64)),
        sa.Column("vault_token_id", sa.String(length=64)),
        sa.Column("payer_email", sa.String(length=254)),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["organizations.id"],
            name=op.f("fk_paypal_funding_accounts_org_id_organizations"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_paypal_funding_accounts")),
    )
    op.create_index(
        op.f("ix_paypal_funding_accounts_org_id"), "paypal_funding_accounts", ["org_id"]
    )
    op.create_table(
        "paypal_vault_sessions",
        sa.Column("id", sa.CHAR(length=36), nullable=False),
        sa.Column("org_id", sa.CHAR(length=36), nullable=False),
        sa.Column("user_id", sa.CHAR(length=36), nullable=False),
        sa.Column("state_hash", sa.CHAR(length=64), nullable=False),
        sa.Column("setup_token_id", sa.String(length=64)),
        sa.Column("return_path", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("failure_reason", sa.String(length=255)),
        sa.Column("expires_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["organizations.id"],
            name=op.f("fk_paypal_vault_sessions_org_id_organizations"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_paypal_vault_sessions_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_paypal_vault_sessions")),
        sa.UniqueConstraint("state_hash", name=op.f("uq_paypal_vault_sessions_state_hash")),
    )
    op.create_index(op.f("ix_paypal_vault_sessions_org_id"), "paypal_vault_sessions", ["org_id"])


def downgrade() -> None:
    op.drop_table("paypal_vault_sessions")
    op.drop_table("paypal_funding_accounts")
    op.drop_table("mandates")
    op.drop_column("organizations", "onboarded_at")
