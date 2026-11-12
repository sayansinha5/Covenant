"""worker description and agent auth token

Revision ID: b7c1e0a49d22
Revises: db910f998626
Create Date: 2026-11-04 00:40:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7c1e0a49d22"
down_revision: str | None = "db910f998626"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("workers", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("workers", sa.Column("auth_token", sa.String(length=255), nullable=True))
    op.add_column("workers", sa.Column("auth_token_hash", sa.CHAR(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("workers", "auth_token_hash")
    op.drop_column("workers", "auth_token")
    op.drop_column("workers", "description")
