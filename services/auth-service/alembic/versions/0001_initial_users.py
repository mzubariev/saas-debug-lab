"""initial users table

Revision ID: 0001
Revises:
Create Date: 2026-03-19 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("hashed_password", sa.String(length=256), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False, server_default="user"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_username", table_name="users")
    op.drop_table("users")
