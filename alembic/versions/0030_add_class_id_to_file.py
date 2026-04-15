"""add optional class_id to file table

Revision ID: 0030_add_class_id_to_file
Revises: 0029_add_cascade_deletes
Create Date: 2026-04-15 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0030_add_class_id_to_file"
down_revision: Union[str, Sequence[str], None] = "0029_add_cascade_deletes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("file", sa.Column("class_id", sa.String(), nullable=True))
    op.create_index(op.f("ix_file_class_id"), "file", ["class_id"], unique=False)
    op.create_foreign_key(
        "file_class_id_fkey",
        "file",
        "class",
        ["class_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("file_class_id_fkey", "file", type_="foreignkey")
    op.drop_index(op.f("ix_file_class_id"), table_name="file")
    op.drop_column("file", "class_id")
