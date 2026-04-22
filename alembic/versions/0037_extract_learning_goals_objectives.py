"""Extract learning_goals and learning_objectives into separate models

Revision ID: 0037_extract_goals_objectives
Revises: 0036_add_school_config_method
Create Date: 2026-04-22 14:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0037_extract_goals_objectives"
down_revision: Union[str, None] = "0036_add_school_config_method"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- learning_goal table ---
    op.create_table(
        "learning_goal",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("overview_id", sa.String(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["overview_id"],
            ["lesplan_overview.id"],
            name="fk_learning_goal_overview_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_learning_goal_overview_id", "learning_goal", ["overview_id"])

    # --- lesson_objective table ---
    op.create_table(
        "lesson_objective",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("lesson_plan_id", sa.String(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["lesson_plan_id"],
            ["lesson_plan.id"],
            name="fk_lesson_objective_lesson_plan_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_lesson_objective_lesson_plan_id", "lesson_objective", ["lesson_plan_id"])

    # --- lesson_objective_goal join table ---
    op.create_table(
        "lesson_objective_goal",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("lesson_objective_id", sa.String(), nullable=False),
        sa.Column("learning_goal_id", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(
            ["lesson_objective_id"],
            ["lesson_objective.id"],
            name="fk_lesson_objective_goal_objective_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["learning_goal_id"],
            ["learning_goal.id"],
            name="fk_lesson_objective_goal_goal_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("lesson_objective_id", "learning_goal_id", name="uq_lesson_objective_goal"),
    )
    op.create_index("ix_lesson_objective_goal_lesson_objective_id", "lesson_objective_goal", ["lesson_objective_id"])
    op.create_index("ix_lesson_objective_goal_learning_goal_id", "lesson_objective_goal", ["learning_goal_id"])

    # --- Migrate existing JSONB data into new tables ---
    # Generate cuid-like IDs using gen_random_uuid() as a stand-in (unique, non-colliding).
    # The app uses cuid2 but for migration purposes uuid strings are fine.

    # Migrate learning_goals from lesplan_overview
    op.execute(sa.text("""
        INSERT INTO learning_goal (id, created_at, updated_at, overview_id, text, position)
        SELECT
            gen_random_uuid()::text,
            lo.created_at,
            lo.updated_at,
            lo.id,
            goal.value::text,
            (goal.ordinality - 1)
        FROM lesplan_overview lo,
        LATERAL jsonb_array_elements_text(lo.learning_goals) WITH ORDINALITY AS goal(value, ordinality)
        WHERE jsonb_array_length(lo.learning_goals) > 0
    """))

    # Migrate learning_objectives from lesson_plan
    op.execute(sa.text("""
        INSERT INTO lesson_objective (id, created_at, updated_at, lesson_plan_id, text, position)
        SELECT
            gen_random_uuid()::text,
            lp.created_at,
            lp.updated_at,
            lp.id,
            obj.value::text,
            (obj.ordinality - 1)
        FROM lesson_plan lp,
        LATERAL jsonb_array_elements_text(lp.learning_objectives) WITH ORDINALITY AS obj(value, ordinality)
        WHERE jsonb_array_length(lp.learning_objectives) > 0
    """))

    # NOTE: lesson_objective_goal is left empty for historical data
    # since no goal attribution exists for previously generated lessons.

    # NOTE: Old JSONB columns (learning_goals, learning_objectives) are intentionally
    # kept on the original tables for backward compatibility.


def downgrade() -> None:
    op.drop_index("ix_lesson_objective_goal_learning_goal_id", table_name="lesson_objective_goal")
    op.drop_index("ix_lesson_objective_goal_lesson_objective_id", table_name="lesson_objective_goal")
    op.drop_table("lesson_objective_goal")
    op.drop_index("ix_lesson_objective_lesson_plan_id", table_name="lesson_objective")
    op.drop_table("lesson_objective")
    op.drop_index("ix_learning_goal_overview_id", table_name="learning_goal")
    op.drop_table("learning_goal")
