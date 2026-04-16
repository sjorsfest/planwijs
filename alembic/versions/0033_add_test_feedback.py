"""add test_feedback, test_feedback_vote, test_feedback_comment tables

Revision ID: 0033_add_test_feedback
Revises: 0032_add_feedback
Create Date: 2026-04-16 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM

# revision identifiers, used by Alembic.
revision: str = "0033_add_test_feedback"
down_revision: Union[str, Sequence[str], None] = "0032_add_feedback"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create enum
    op.execute(
        "DO $$ BEGIN CREATE TYPE test_feedback_type AS ENUM ('BUG', 'SUGGESTION', 'OTHER'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
    )

    # test_feedback
    op.create_table(
        "test_feedback",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("route", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("type", ENUM("BUG", "SUGGESTION", "OTHER", name="test_feedback_type", create_type=False), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_test_feedback_user_id", "test_feedback", ["user_id"])

    # test_feedback_vote
    op.create_table(
        "test_feedback_vote",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("feedback_id", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["feedback_id"], ["test_feedback.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "feedback_id", name="uq_test_feedback_vote_user_feedback"),
    )
    op.create_index("ix_test_feedback_vote_user_id", "test_feedback_vote", ["user_id"])
    op.create_index("ix_test_feedback_vote_feedback_id", "test_feedback_vote", ["feedback_id"])

    # test_feedback_comment
    op.create_table(
        "test_feedback_comment",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("feedback_id", sa.String(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["feedback_id"], ["test_feedback.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_test_feedback_comment_user_id", "test_feedback_comment", ["user_id"])
    op.create_index("ix_test_feedback_comment_feedback_id", "test_feedback_comment", ["feedback_id"])


def downgrade() -> None:
    op.drop_table("test_feedback_comment")
    op.drop_table("test_feedback_vote")
    op.drop_table("test_feedback")
    sa.Enum(name="test_feedback_type").drop(op.get_bind())
