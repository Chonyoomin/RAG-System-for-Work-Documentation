"""initial schema: enable pgvector and create system_info

Revision ID: 0001
Revises:
Create Date: 2026-05-10

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "system_info",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("value", sa.String(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("key", name="uq_system_info_key"),
    )
    op.create_index("ix_system_info_key", "system_info", ["key"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_system_info_key", table_name="system_info")
    op.drop_table("system_info")
    op.execute("DROP EXTENSION IF EXISTS vector")
