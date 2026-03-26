"""add lesplan tables

Revision ID: 0007_add_lesplan_tables
Revises: 0006_remove_legacy_subject
Create Date: 2026-03-26 18:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_add_lesplan_tables"
down_revision: Union[str, Sequence[str], None] = "0006_remove_legacy_subject"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_LESPLAN_STATUS_VALUES = (
    "PENDING",
    "GENERATING_OVERVIEW",
    "OVERVIEW_READY",
    "REVISING_OVERVIEW",
    "GENERATING_LESSONS",
    "COMPLETED",
    "FAILED",
)


def upgrade() -> None:
    values = ", ".join(f"'{v}'" for v in _LESPLAN_STATUS_VALUES)
    op.execute(f"CREATE TYPE lesplan_status AS ENUM ({values})")

    op.create_table(
        "lesplan_request",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("user_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("class_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("book_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("selected_paragraph_ids", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("num_lessons", sa.Integer(), nullable=False),
        sa.Column("lesson_duration_minutes", sa.Integer(), nullable=False),
        sa.Column("status", postgresql.ENUM(name="lesplan_status", create_type=False), nullable=False),
        sa.CheckConstraint("num_lessons >= 1", name="ck_lesplan_request_num_lessons"),
        sa.CheckConstraint("lesson_duration_minutes >= 1", name="ck_lesplan_request_lesson_duration"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["class_id"], ["class.id"]),
        sa.ForeignKeyConstraint(["book_id"], ["book.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_lesplan_request_user_id"), "lesplan_request", ["user_id"], unique=False)
    op.create_index(op.f("ix_lesplan_request_class_id"), "lesplan_request", ["class_id"], unique=False)
    op.create_index(op.f("ix_lesplan_request_book_id"), "lesplan_request", ["book_id"], unique=False)

    op.create_table(
        "lesplan_overview",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("request_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("title", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("summary", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("pedagogical_rationale", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("interactivity_approach", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("teaching_structure", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.ForeignKeyConstraint(["request_id"], ["lesplan_request.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("request_id", name="uq_lesplan_overview_request_id"),
    )
    op.create_index(op.f("ix_lesplan_overview_request_id"), "lesplan_overview", ["request_id"], unique=True)

    op.create_table(
        "lesson_plan",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("overview_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("lesson_number", sa.Integer(), nullable=False),
        sa.Column("title", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("learning_objectives", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("time_sections", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("required_materials", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("covered_paragraph_ids", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("teacher_notes", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.CheckConstraint("lesson_number >= 1", name="ck_lesson_plan_lesson_number"),
        sa.ForeignKeyConstraint(["overview_id"], ["lesplan_overview.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_lesson_plan_overview_id"), "lesson_plan", ["overview_id"], unique=False)

    op.create_table(
        "lesplan_feedback_message",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("request_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("role", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("content", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.ForeignKeyConstraint(["request_id"], ["lesplan_request.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_lesplan_feedback_message_request_id"),
        "lesplan_feedback_message",
        ["request_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_lesplan_feedback_message_request_id"),
        table_name="lesplan_feedback_message",
    )
    op.drop_table("lesplan_feedback_message")

    op.drop_index(op.f("ix_lesson_plan_overview_id"), table_name="lesson_plan")
    op.drop_table("lesson_plan")

    op.drop_index(op.f("ix_lesplan_overview_request_id"), table_name="lesplan_overview")
    op.drop_table("lesplan_overview")

    op.drop_index(op.f("ix_lesplan_request_book_id"), table_name="lesplan_request")
    op.drop_index(op.f("ix_lesplan_request_class_id"), table_name="lesplan_request")
    op.drop_index(op.f("ix_lesplan_request_user_id"), table_name="lesplan_request")
    op.drop_table("lesplan_request")

    op.execute("DROP TYPE lesplan_status")
