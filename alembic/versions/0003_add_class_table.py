"""add class table

Revision ID: 0003_add_class_table
Revises: 0002_add_book_chapter_paragraph
Create Date: 2026-03-25 18:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_add_class_table"
down_revision: Union[str, Sequence[str], None] = "0002_add_book_chapter_paragraph"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_LEVEL_VALUES = (
    "HAVO",
    "VWO",
    "GYMNASIUM",
    "VMBO_B",
    "VMBO_K",
    "VMBO_G",
    "VMBO_T",
    "UNKNOWN",
)
_SCHOOL_YEAR_VALUES = (
    "YEAR_1",
    "YEAR_2",
    "YEAR_3",
    "YEAR_4",
    "YEAR_5",
    "YEAR_6",
    "UNKNOWN",
)
_CLASS_DIFFICULTY_VALUES = ("GREEN", "ORANGE", "RED")


def upgrade() -> None:
    level_values = ", ".join(f"'{v}'" for v in _LEVEL_VALUES)
    school_year_values = ", ".join(f"'{v}'" for v in _SCHOOL_YEAR_VALUES)
    difficulty_values = ", ".join(f"'{v}'" for v in _CLASS_DIFFICULTY_VALUES)

    op.execute(f"CREATE TYPE level AS ENUM ({level_values})")
    op.execute(f"CREATE TYPE school_year AS ENUM ({school_year_values})")
    op.execute(f"CREATE TYPE class_difficulty AS ENUM ({difficulty_values})")

    op.create_table(
        "class",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("user_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("subject", postgresql.ENUM(name="subject", create_type=False), nullable=False),
        sa.Column("level", postgresql.ENUM(name="level", create_type=False), nullable=False),
        sa.Column("school_year", postgresql.ENUM(name="school_year", create_type=False), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("difficulty", postgresql.ENUM(name="class_difficulty", create_type=False), nullable=False),
        sa.CheckConstraint("size >= 0", name="ck_class_size_non_negative"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_class_user_id"), "class", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_class_user_id"), table_name="class")
    op.drop_table("class")
    op.execute("DROP TYPE class_difficulty")
    op.execute("DROP TYPE school_year")
    op.execute("DROP TYPE level")
