"""add feedback table for tracking user feedback on generated content

Revision ID: 0032_add_feedback
Revises: 0031_add_organizations
Create Date: 2026-04-15 16:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM

# revision identifiers, used by Alembic.
revision: str = "0032_add_feedback"
down_revision: Union[str, Sequence[str], None] = "0031_add_organizations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "DO $$ BEGIN CREATE TYPE feedback_target_type AS ENUM ('LESPLAN_OVERVIEW', 'LESSON_PLAN'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
    )

    op.create_table(
        "feedback",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("target_type", ENUM("LESPLAN_OVERVIEW", "LESSON_PLAN", name="feedback_target_type", create_type=False), nullable=False),
        sa.Column("target_id", sa.String(), nullable=False),
        sa.Column("field_name", sa.String(), nullable=False),
        sa.Column("original_text", sa.Text(), nullable=True),
        sa.Column("feedback_text", sa.Text(), nullable=False),
        sa.Column("organization_id", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organization.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_feedback_user_id", "feedback", ["user_id"])
    op.create_index("ix_feedback_target_id", "feedback", ["target_id"])
    op.create_index("ix_feedback_organization_id", "feedback", ["organization_id"])


def downgrade() -> None:
    op.drop_table("feedback")
    sa.Enum(name="feedback_target_type").drop(op.get_bind())
