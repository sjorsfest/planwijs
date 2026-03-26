"""make class difficulty nullable

Revision ID: 0004_class_difficulty_nullable
Revises: 0003_add_class_table
Create Date: 2026-03-25 18:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_class_difficulty_nullable"
down_revision: Union[str, Sequence[str], None] = "0003_add_class_table"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "class",
        "difficulty",
        existing_type=postgresql.ENUM(name="class_difficulty", create_type=False),
        nullable=True,
    )


def downgrade() -> None:
    op.execute("UPDATE class SET difficulty = 'GREEN' WHERE difficulty IS NULL")
    op.alter_column(
        "class",
        "difficulty",
        existing_type=postgresql.ENUM(name="class_difficulty", create_type=False),
        nullable=False,
    )
