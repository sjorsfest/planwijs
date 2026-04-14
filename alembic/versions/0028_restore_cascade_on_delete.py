"""restore cascade on delete for all foreign keys

Revision ID: 0028_restore_cascade_on_delete
Revises: 0027_fix_the_db_drift_and_sync_s
Create Date: 2026-04-14 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0028_restore_cascade_on_delete"
down_revision: Union[str, Sequence[str], None] = "0027_fix_the_db_drift_and_sync_s"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (table, constraint_name, local_col, ref_table, ref_col, on_delete)
_FK_CASCADE = [
    ("class", "class_user_id_fkey", "user_id", "user", "id", "CASCADE"),
    ("book", "book_subject_id_fkey", "subject_id", "subjects", "id", "SET NULL"),
    ("lesplan_request", "lesplan_request_user_id_fkey", "user_id", "user", "id", "CASCADE"),
    ("lesplan_request", "lesplan_request_class_id_fkey", "class_id", "class", "id", "CASCADE"),
    ("lesplan_overview", "lesplan_overview_request_id_fkey", "request_id", "lesplan_request", "id", "CASCADE"),
    ("lesson_plan", "lesson_plan_overview_id_fkey", "overview_id", "lesplan_overview", "id", "CASCADE"),
    ("lesson_preparation_todo", "lesson_preparation_todo_lesson_plan_id_fkey", "lesson_plan_id", "lesson_plan", "id", "CASCADE"),
]


def upgrade() -> None:
    for table, name, local_col, ref_table, ref_col, on_delete in _FK_CASCADE:
        # Drop the existing constraint (without CASCADE)
        op.drop_constraint(name, table, type_="foreignkey")
        # Recreate with ondelete
        op.create_foreign_key(
            name, table, ref_table, [local_col], [ref_col], ondelete=on_delete
        )


def downgrade() -> None:
    for table, name, local_col, ref_table, ref_col, _on_delete in _FK_CASCADE:
        op.drop_constraint(name, table, type_="foreignkey")
        op.create_foreign_key(name, table, ref_table, [local_col], [ref_col])
