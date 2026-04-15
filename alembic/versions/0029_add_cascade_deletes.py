"""add cascade on delete to remaining foreign keys

Revision ID: 0029_add_cascade_deletes
Revises: 0028_restore_cascade_on_delete
Create Date: 2026-04-14 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0029_add_cascade_deletes"
down_revision: Union[str, Sequence[str], None] = "0028_restore_cascade_on_delete"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (table, constraint_name, local_col, ref_table, ref_col, ondelete)
_FK_RULES = [
    # Required FKs → CASCADE (child can't exist without parent)
    ("file", "file_user_id_fkey", "user_id", "user", "id", "CASCADE"),
    ("folder", "folder_user_id_fkey", "user_id", "user", "id", "CASCADE"),
    ("classroom", "classroom_user_id_fkey", "user_id", "user", "id", "CASCADE"),
    ("book_chapter", "book_chapter_book_id_fkey", "book_id", "book", "id", "CASCADE"),
    ("book_chapter_paragraph", "book_chapter_paragraph_chapter_id_fkey", "chapter_id", "book_chapter", "id", "CASCADE"),
    # Optional FKs → SET NULL (child survives, link is cleared)
    ("file", "file_lesplan_request_id_fkey", "lesplan_request_id", "lesplan_request", "id", "SET NULL"),
    ("file", "fk_file_folder_id", "folder_id", "folder", "id", "SET NULL"),
    ("folder", "folder_parent_id_fkey", "parent_id", "folder", "id", "SET NULL"),
]


def upgrade() -> None:
    for table, name, local_col, ref_table, ref_col, ondelete in _FK_RULES:
        op.drop_constraint(name, table, type_="foreignkey")
        op.create_foreign_key(
            name, table, ref_table, [local_col], [ref_col], ondelete=ondelete
        )


def downgrade() -> None:
    for table, name, local_col, ref_table, ref_col, _ondelete in _FK_RULES:
        op.drop_constraint(name, table, type_="foreignkey")
        op.create_foreign_key(name, table, ref_table, [local_col], [ref_col])
