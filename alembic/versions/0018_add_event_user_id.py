"""add user_id to event table

Revision ID: 0018_add_event_user_id
Revises: 0017_add_class_profile_fields
Create Date: 2026-04-07 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0018_add_event_user_id"
down_revision: Union[str, None] = "0017_add_class_profile_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("event", sa.Column("user_id", sa.String(), nullable=True))

    # Set user_id for existing events to the first user (if any exist)
    op.execute(
        """
        UPDATE event
        SET user_id = (SELECT id FROM "user" LIMIT 1)
        WHERE user_id IS NULL
        """
    )

    op.alter_column("event", "user_id", nullable=False)
    op.create_index(op.f("ix_event_user_id"), "event", ["user_id"], unique=False)
    op.create_foreign_key("fk_event_user_id", "event", "user", ["user_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint("fk_event_user_id", "event", type_="foreignkey")
    op.drop_index(op.f("ix_event_user_id"), table_name="event")
    op.drop_column("event", "user_id")
