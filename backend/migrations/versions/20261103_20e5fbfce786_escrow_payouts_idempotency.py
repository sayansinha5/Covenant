"""escrow: PayPal holds, provider payouts, idempotency keys

Revision ID: 20e5fbfce786
Revises: 4135e91b105c
Create Date: 2026-11-03 16:19:44.314462
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "20e5fbfce786"
down_revision: str | None = "4135e91b105c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MONEY = sa.Numeric(precision=12, scale=2)
UUID = sa.CHAR(length=36)
TIMESTAMP = mysql.DATETIME(fsp=6)
PAYPAL_ID = sa.String(length=64)


def _fk(table: str, column: str, target: str) -> sa.ForeignKeyConstraint:
    referred = target.split(".")[0]
    return sa.ForeignKeyConstraint([column], [target], name=op.f(f"fk_{table}_{column}_{referred}"))


def upgrade() -> None:
    op.create_table(
        "escrows",
        sa.Column("id", UUID, nullable=False),
        sa.Column("contract_id", UUID, nullable=False),
        sa.Column("org_id", UUID, nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("request_series", sa.Integer(), nullable=False),
        sa.Column("amount", MONEY, nullable=False),
        sa.Column("currency", sa.CHAR(length=3), nullable=False),
        sa.Column("paypal_order_id", PAYPAL_ID),
        sa.Column("paypal_authorization_id", PAYPAL_ID),
        sa.Column("paypal_capture_id", PAYPAL_ID),
        sa.Column("payer_action_url", sa.String(length=2048)),
        sa.Column("amount_held", MONEY, nullable=False),
        sa.Column("amount_captured", MONEY, nullable=False),
        sa.Column("amount_released", MONEY, nullable=False),
        sa.Column("settlement", sa.JSON()),
        sa.Column("failure_reason", sa.String(length=500)),
        sa.Column("reserved_at", TIMESTAMP, nullable=False),
        sa.Column("auth_expires_at", TIMESTAMP),
        sa.Column("honor_period_ends_at", TIMESTAMP),
        sa.Column("reauthorized_at", TIMESTAMP),
        sa.Column("created_at", TIMESTAMP, nullable=False),
        sa.Column("updated_at", TIMESTAMP, nullable=False),
        _fk("escrows", "contract_id", "contracts.id"),
        _fk("escrows", "org_id", "organizations.id"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_escrows")),
        sa.UniqueConstraint("contract_id", name=op.f("uq_escrows_contract_id")),
    )
    op.create_index(op.f("ix_escrows_org_id_reserved_at"), "escrows", ["org_id", "reserved_at"])
    op.create_index(op.f("ix_escrows_status"), "escrows", ["status"])
    op.create_index(op.f("ix_escrows_paypal_order_id"), "escrows", ["paypal_order_id"])
    op.create_index(
        op.f("ix_escrows_paypal_authorization_id"), "escrows", ["paypal_authorization_id"]
    )

    op.create_table(
        "payouts",
        sa.Column("id", UUID, nullable=False),
        sa.Column("contract_id", UUID, nullable=False),
        sa.Column("provider_org_id", UUID, nullable=False),
        sa.Column("receiver_email", sa.String(length=254)),
        sa.Column("gross", MONEY, nullable=False),
        sa.Column("fee", MONEY, nullable=False),
        sa.Column("net", MONEY, nullable=False),
        sa.Column("currency", sa.CHAR(length=3), nullable=False),
        sa.Column("sender_batch_id", PAYPAL_ID, nullable=False),
        sa.Column("paypal_batch_id", PAYPAL_ID),
        sa.Column("paypal_item_id", PAYPAL_ID),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("failure_reason", sa.String(length=500)),
        sa.Column("created_at", TIMESTAMP, nullable=False),
        sa.Column("updated_at", TIMESTAMP, nullable=False),
        _fk("payouts", "contract_id", "contracts.id"),
        _fk("payouts", "provider_org_id", "organizations.id"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payouts")),
        sa.UniqueConstraint("contract_id", name=op.f("uq_payouts_contract_id")),
        sa.UniqueConstraint("sender_batch_id", name=op.f("uq_payouts_sender_batch_id")),
    )
    op.create_index(
        op.f("ix_payouts_provider_org_id_created_at"), "payouts", ["provider_org_id", "created_at"]
    )

    op.create_table(
        "idempotency_keys",
        sa.Column("org_id", UUID, nullable=False),
        sa.Column("route", sa.String(length=100), nullable=False),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("request_hash", sa.CHAR(length=64), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=False),
        sa.Column("response_body", sa.JSON(), nullable=False),
        sa.Column("created_at", TIMESTAMP, nullable=False),
        sa.PrimaryKeyConstraint("org_id", "route", "key", name=op.f("pk_idempotency_keys")),
    )


def downgrade() -> None:
    op.drop_table("idempotency_keys")
    op.drop_table("payouts")
    op.drop_table("escrows")
