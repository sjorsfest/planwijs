"""add revising_lesson status and outdated field on preparation todos

Revision ID: 0035_add_lesson_feedback_support
Revises: 0034_school_config_user_subjects
Create Date: 2026-04-17 18:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0035_add_lesson_feedback_support"
down_revision: Union[str, None] = "0034_school_config_user_subjects"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE lesplan_status ADD VALUE IF NOT EXISTS 'REVISING_LESSON'")
    op.add_column(
        "lesson_preparation_todo",
        sa.Column("outdated", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("lesson_preparation_todo", "outdated")
