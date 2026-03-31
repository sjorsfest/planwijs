"""add class profile fields: attention_span_minutes, support_challenge, class_notes

Revision ID: 0017_add_class_profile_fields
Revises: 0016_fix_preparation_status
Create Date: 2026-03-31 14:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0017_add_class_profile_fields"
down_revision: Union[str, Sequence[str], None] = "0016_fix_preparation_status"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    class_support_challenge = sa.Enum(
        "Meer ondersteuning",
        "Gebalanceerd",
        "Meer uitdaging",
        name="class_support_challenge",
    )
    class_support_challenge.create(op.get_bind(), checkfirst=True)

    op.add_column("class", sa.Column("attention_span_minutes", sa.Integer(), nullable=True))
    op.add_column(
        "class",
        sa.Column(
            "support_challenge",
            class_support_challenge,
            nullable=True,
        ),
    )
    op.add_column("class", sa.Column("class_notes", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("class", "class_notes")
    op.drop_column("class", "support_challenge")
    op.drop_column("class", "attention_span_minutes")
    sa.Enum(name="class_support_challenge").drop(op.get_bind(), checkfirst=True)
