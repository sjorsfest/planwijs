"""add learning_progression column and builds_on inside lesson_outline

Revision ID: 0010_learning_progression
Revises: 0009_lesplan_overview_fields
Create Date: 2026-03-26 21:00:00.000000

builds_on is stored inside the lesson_outline JSONB array — no schema change needed for it.
learning_progression is a new text column on lesplan_overview.
"""

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "0010_learning_progression"
down_revision: Union[str, Sequence[str], None] = "0009_lesplan_overview_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "lesplan_overview",
        sa.Column("learning_progression", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    )
    op.execute("UPDATE lesplan_overview SET learning_progression = '' WHERE learning_progression IS NULL")
    op.alter_column("lesplan_overview", "learning_progression", nullable=False)


def downgrade() -> None:
    op.drop_column("lesplan_overview", "learning_progression")
