"""add review-first overview contract fields

Revision ID: 0015_review_overview_contract
Revises: 0014_cascade_user_deletes
Create Date: 2026-03-27 17:30:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015_review_overview_contract"
down_revision: Union[str, Sequence[str], None] = "0014_cascade_user_deletes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "lesplan_overview",
        sa.Column("series_summary", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    )
    op.execute(
        """
        UPDATE lesplan_overview
        SET series_summary = COALESCE(NULLIF(learning_progression, ''), '')
        WHERE series_summary IS NULL
        """
    )
    op.alter_column("lesplan_overview", "series_summary", nullable=False)

    op.add_column(
        "lesplan_overview",
        sa.Column("series_themes", postgresql.JSONB(), nullable=False, server_default="[]"),
    )
    op.execute(
        """
        UPDATE lesplan_overview
        SET series_themes = COALESCE(
            (
                SELECT jsonb_agg(value)
                FROM (
                    SELECT value
                    FROM jsonb_array_elements_text(key_knowledge) AS value
                    LIMIT 5
                ) AS top_values
            ),
            '[]'::jsonb
        )
        WHERE series_themes = '[]'::jsonb
        """
    )

    op.add_column(
        "lesplan_overview",
        sa.Column("goal_coverage", postgresql.JSONB(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "lesplan_overview",
        sa.Column("knowledge_coverage", postgresql.JSONB(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "lesplan_overview",
        sa.Column("approval_readiness", postgresql.JSONB(), nullable=False, server_default="{}"),
    )

    op.execute(
        """
        UPDATE lesplan_overview
        SET approval_readiness = jsonb_build_object(
            'ready_for_approval', false,
            'rationale', 'Controleer of doelen, kernkennis en opbouw kloppen voordat je goedkeurt.',
            'checklist', jsonb_build_array(
                'Doelen sluiten aan op de klas.',
                'Kernkennis is volledig en correct.',
                'Lesvolgorde bouwt logisch op.'
            ),
            'open_questions', '[]'::jsonb
        )
        WHERE approval_readiness = '{}'::jsonb
        """
    )


def downgrade() -> None:
    op.drop_column("lesplan_overview", "approval_readiness")
    op.drop_column("lesplan_overview", "knowledge_coverage")
    op.drop_column("lesplan_overview", "goal_coverage")
    op.drop_column("lesplan_overview", "series_themes")
    op.drop_column("lesplan_overview", "series_summary")
