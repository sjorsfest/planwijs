"""add optional planned_date to lesson_plan

Revision ID: 0013_lesson_plan_planned_date
Revises: 0012_lesson_preparation_todos
Create Date: 2026-03-27 00:00:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0013_lesson_plan_planned_date"
down_revision: Union[str, Sequence[str], None] = "0012_lesson_preparation_todos"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("lesson_plan", sa.Column("planned_date", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("lesson_plan", "planned_date")
