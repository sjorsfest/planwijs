"""update lesplan_overview fields to elaborate synopsis structure

Revision ID: 0009_lesplan_overview_fields
Revises: 0008_lesplan_status_case
Create Date: 2026-03-26 20:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_lesplan_overview_fields"
down_revision: Union[str, Sequence[str], None] = "0008_lesplan_status_case"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new columns
    op.add_column("lesplan_overview", sa.Column("learning_goals", sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.add_column("lesplan_overview", sa.Column("key_knowledge", postgresql.JSONB(), nullable=True, server_default="[]"))
    op.add_column("lesplan_overview", sa.Column("recommended_approach", sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.add_column("lesplan_overview", sa.Column("lesson_outline", postgresql.JSONB(), nullable=True, server_default="[]"))
    op.add_column("lesplan_overview", sa.Column("didactic_approach", sqlmodel.sql.sqltypes.AutoString(), nullable=True))

    # Migrate data from old columns into new ones (best-effort)
    op.execute("""
        UPDATE lesplan_overview SET
            learning_goals = COALESCE(teaching_structure, ''),
            key_knowledge = '[]'::jsonb,
            recommended_approach = COALESCE(pedagogical_rationale, ''),
            lesson_outline = '[]'::jsonb,
            didactic_approach = COALESCE(summary || E'\n\n' || interactivity_approach, '')
        WHERE learning_goals IS NULL
    """)

    # Make new columns NOT NULL now that data is migrated
    op.alter_column("lesplan_overview", "learning_goals", nullable=False)
    op.alter_column("lesplan_overview", "key_knowledge", nullable=False)
    op.alter_column("lesplan_overview", "recommended_approach", nullable=False)
    op.alter_column("lesplan_overview", "lesson_outline", nullable=False)
    op.alter_column("lesplan_overview", "didactic_approach", nullable=False)

    # Drop old columns
    op.drop_column("lesplan_overview", "summary")
    op.drop_column("lesplan_overview", "pedagogical_rationale")
    op.drop_column("lesplan_overview", "interactivity_approach")
    op.drop_column("lesplan_overview", "teaching_structure")


def downgrade() -> None:
    # Re-add old columns
    op.add_column("lesplan_overview", sa.Column("summary", sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.add_column("lesplan_overview", sa.Column("pedagogical_rationale", sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.add_column("lesplan_overview", sa.Column("interactivity_approach", sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.add_column("lesplan_overview", sa.Column("teaching_structure", sqlmodel.sql.sqltypes.AutoString(), nullable=True))

    op.execute("""
        UPDATE lesplan_overview SET
            summary = COALESCE(didactic_approach, ''),
            pedagogical_rationale = COALESCE(recommended_approach, ''),
            interactivity_approach = '',
            teaching_structure = COALESCE(learning_goals, '')
        WHERE summary IS NULL
    """)

    op.alter_column("lesplan_overview", "summary", nullable=False)
    op.alter_column("lesplan_overview", "pedagogical_rationale", nullable=False)
    op.alter_column("lesplan_overview", "interactivity_approach", nullable=False)
    op.alter_column("lesplan_overview", "teaching_structure", nullable=False)

    # Drop new columns
    op.drop_column("lesplan_overview", "learning_goals")
    op.drop_column("lesplan_overview", "key_knowledge")
    op.drop_column("lesplan_overview", "recommended_approach")
    op.drop_column("lesplan_overview", "lesson_outline")
    op.drop_column("lesplan_overview", "didactic_approach")
