"""add lesson_preparation_todo table

Revision ID: 0012_lesson_preparation_todos
Revises: 0011_learning_goals_jsonb
Create Date: 2026-03-27 00:00:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012_lesson_preparation_todos"
down_revision: Union[str, Sequence[str], None] = "0011_learning_goals_jsonb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE TYPE lesson_preparation_status AS ENUM ('pending', 'done')")

    op.create_table(
        "lesson_preparation_todo",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("lesson_plan_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("title", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("description", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("why", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM("pending", "done", name="lesson_preparation_status", create_type=False),
            nullable=False,
        ),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(["lesson_plan_id"], ["lesson_plan.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_lesson_preparation_todo_lesson_plan_id"),
        "lesson_preparation_todo",
        ["lesson_plan_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_lesson_preparation_todo_lesson_plan_id"),
        table_name="lesson_preparation_todo",
    )
    op.drop_table("lesson_preparation_todo")
    op.execute("DROP TYPE lesson_preparation_status")
