"""add school_config_method many-to-many link table

Revision ID: 0036_add_school_config_method
Revises: 0035_add_lesson_feedback_support
Create Date: 2026-04-22 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0036_add_school_config_method"
down_revision: Union[str, None] = "0035_add_lesson_feedback_support"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "school_config_method",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("school_config_id", sa.String(), nullable=False),
        sa.Column("method_id", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(
            ["school_config_id"],
            ["school_config.id"],
            name="fk_school_config_method_school_config_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["method_id"],
            ["method.id"],
            name="fk_school_config_method_method_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("school_config_id", "method_id", name="uq_school_config_method"),
    )
    op.create_index("ix_school_config_method_school_config_id", "school_config_method", ["school_config_id"])
    op.create_index("ix_school_config_method_method_id", "school_config_method", ["method_id"])


def downgrade() -> None:
    op.drop_index("ix_school_config_method_method_id", table_name="school_config_method")
    op.drop_index("ix_school_config_method_school_config_id", table_name="school_config_method")
    op.drop_table("school_config_method")
