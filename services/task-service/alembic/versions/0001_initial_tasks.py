"""initial tasks table

Revision ID: 0001
Revises:
Create Date: 2026-03-19 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# The Postgres enum type must be created before the table that references it.
_taskstatus_enum = sa.Enum(
    "created", "in_progress", "completed",
    name="taskstatus",
)


def upgrade() -> None:
    _taskstatus_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "tasks",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column(
            "status",
            _taskstatus_enum,
            nullable=False,
            server_default="created",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("ix_tasks_status",     "tasks", ["status"])
    op.create_index("ix_tasks_created_at", "tasks", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_tasks_created_at", table_name="tasks")
    op.drop_index("ix_tasks_status",     table_name="tasks")
    op.drop_table("tasks")
    _taskstatus_enum.drop(op.get_bind(), checkfirst=True)
