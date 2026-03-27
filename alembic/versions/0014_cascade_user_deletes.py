"""cascade user-owned data deletes

Revision ID: 0014_cascade_user_deletes
Revises: 0013_lesson_plan_planned_date
Create Date: 2026-03-27 00:00:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0014_cascade_user_deletes"
down_revision: Union[str, Sequence[str], None] = "0013_lesson_plan_planned_date"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("class_user_id_fkey", "class", type_="foreignkey")
    op.create_foreign_key(
        "class_user_id_fkey",
        "class",
        "user",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.drop_constraint("lesplan_request_user_id_fkey", "lesplan_request", type_="foreignkey")
    op.create_foreign_key(
        "lesplan_request_user_id_fkey",
        "lesplan_request",
        "user",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.drop_constraint("lesplan_request_class_id_fkey", "lesplan_request", type_="foreignkey")
    op.create_foreign_key(
        "lesplan_request_class_id_fkey",
        "lesplan_request",
        "class",
        ["class_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.drop_constraint("lesplan_overview_request_id_fkey", "lesplan_overview", type_="foreignkey")
    op.create_foreign_key(
        "lesplan_overview_request_id_fkey",
        "lesplan_overview",
        "lesplan_request",
        ["request_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.drop_constraint("lesson_plan_overview_id_fkey", "lesson_plan", type_="foreignkey")
    op.create_foreign_key(
        "lesson_plan_overview_id_fkey",
        "lesson_plan",
        "lesplan_overview",
        ["overview_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.drop_constraint("lesplan_feedback_message_request_id_fkey", "lesplan_feedback_message", type_="foreignkey")
    op.create_foreign_key(
        "lesplan_feedback_message_request_id_fkey",
        "lesplan_feedback_message",
        "lesplan_request",
        ["request_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.drop_constraint("lesson_preparation_todo_lesson_plan_id_fkey", "lesson_preparation_todo", type_="foreignkey")
    op.create_foreign_key(
        "lesson_preparation_todo_lesson_plan_id_fkey",
        "lesson_preparation_todo",
        "lesson_plan",
        ["lesson_plan_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("lesson_preparation_todo_lesson_plan_id_fkey", "lesson_preparation_todo", type_="foreignkey")
    op.create_foreign_key(
        "lesson_preparation_todo_lesson_plan_id_fkey",
        "lesson_preparation_todo",
        "lesson_plan",
        ["lesson_plan_id"],
        ["id"],
    )

    op.drop_constraint("lesplan_feedback_message_request_id_fkey", "lesplan_feedback_message", type_="foreignkey")
    op.create_foreign_key(
        "lesplan_feedback_message_request_id_fkey",
        "lesplan_feedback_message",
        "lesplan_request",
        ["request_id"],
        ["id"],
    )

    op.drop_constraint("lesson_plan_overview_id_fkey", "lesson_plan", type_="foreignkey")
    op.create_foreign_key(
        "lesson_plan_overview_id_fkey",
        "lesson_plan",
        "lesplan_overview",
        ["overview_id"],
        ["id"],
    )

    op.drop_constraint("lesplan_overview_request_id_fkey", "lesplan_overview", type_="foreignkey")
    op.create_foreign_key(
        "lesplan_overview_request_id_fkey",
        "lesplan_overview",
        "lesplan_request",
        ["request_id"],
        ["id"],
    )

    op.drop_constraint("lesplan_request_class_id_fkey", "lesplan_request", type_="foreignkey")
    op.create_foreign_key(
        "lesplan_request_class_id_fkey",
        "lesplan_request",
        "class",
        ["class_id"],
        ["id"],
    )

    op.drop_constraint("lesplan_request_user_id_fkey", "lesplan_request", type_="foreignkey")
    op.create_foreign_key(
        "lesplan_request_user_id_fkey",
        "lesplan_request",
        "user",
        ["user_id"],
        ["id"],
    )

    op.drop_constraint("class_user_id_fkey", "class", type_="foreignkey")
    op.create_foreign_key(
        "class_user_id_fkey",
        "class",
        "user",
        ["user_id"],
        ["id"],
    )
