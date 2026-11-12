"""paypal operations audit

Revision ID: 3739e707b493
Revises:
Create Date: 2026-11-03 07:49:03.799004
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "3739e707b493"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "paypal_operations",
        sa.Column("id", sa.CHAR(length=36), nullable=False),
        sa.Column("contract_id", sa.CHAR(length=36), nullable=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("request_id", sa.String(length=108), nullable=False),
        sa.Column("http_method", sa.String(length=8), nullable=False),
        sa.Column("path", sa.String(length=255), nullable=False),
        sa.Column("request_body", sa.JSON(), nullable=True),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("response_body", sa.JSON(), nullable=True),
        sa.Column("paypal_debug_id", sa.String(length=64), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_paypal_operations")),
        sa.UniqueConstraint("request_id", name=op.f("uq_paypal_operations_request_id")),
    )
    op.create_index(op.f("ix_paypal_operations_contract_id"), "paypal_operations", ["contract_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_paypal_operations_contract_id"), table_name="paypal_operations")
    op.drop_table("paypal_operations")
