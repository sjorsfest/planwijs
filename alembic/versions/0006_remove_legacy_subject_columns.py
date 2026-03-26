"""remove legacy subject columns from books and subjects

Revision ID: 0006_remove_legacy_subject_columns
Revises: 0005_add_subject_book_relation
Create Date: 2026-03-26 16:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_remove_legacy_subject_columns"
down_revision: Union[str, Sequence[str], None] = "0005_add_subject_book_relation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SLUG_TO_SUBJECT_ENUM: tuple[tuple[str, str], ...] = (
    ("nederlands", "NEDERLANDS"),
    ("engels", "ENGELS"),
    ("duits", "DUITS"),
    ("frans", "FRANS"),
    ("spaans", "SPAANS"),
    ("grieks", "GRIEKS"),
    ("latijn", "LATIJN"),
    ("wiskunde", "WISKUNDE"),
    ("wiskunde-a", "WISKUNDE_A"),
    ("wiskunde-b", "WISKUNDE_B"),
    ("natuurkunde", "NATUURKUNDE"),
    ("scheikunde", "SCHEIKUNDE"),
    ("biologie", "BIOLOGIE"),
    ("nask-science", "NASK_SCIENCE"),
    ("aardrijkskunde", "AARDRIJKSKUNDE"),
    ("geschiedenis", "GESCHIEDENIS"),
    ("maatschappijleer", "MAATSCHAPPIJLEER"),
    ("maw", "MAW"),
    ("mens-en-maatschappij", "MENS_EN_MAATSCHAPPIJ"),
    ("levensbeschouwing", "LEVENS_BESCHOUWING"),
    ("economie", "ECONOMIE"),
    ("bedrijfseconomie", "BEDRIJFSECONOMIE"),
)


def upgrade() -> None:
    op.drop_column("book", "subject")
    op.drop_column("subjects", "legacy_subject")


def downgrade() -> None:
    op.add_column(
        "subjects",
        sa.Column("legacy_subject", postgresql.ENUM(name="subject", create_type=False), nullable=True),
    )

    subject_case = " ".join(
        f"WHEN slug = '{slug}' THEN '{subject_enum}'::subject"
        for slug, subject_enum in _SLUG_TO_SUBJECT_ENUM
    )
    op.execute(
        f"""
        UPDATE subjects
        SET legacy_subject = CASE
            {subject_case}
            ELSE 'UNKNOWN'::subject
        END
        """
    )
    op.alter_column(
        "subjects",
        "legacy_subject",
        existing_type=postgresql.ENUM(name="subject", create_type=False),
        nullable=False,
    )
    op.create_unique_constraint("uq_subjects_legacy_subject", "subjects", ["legacy_subject"])

    op.add_column(
        "book",
        sa.Column("subject", postgresql.ENUM(name="subject", create_type=False), nullable=True),
    )
    op.execute(
        """
        UPDATE book
        SET subject = subjects.legacy_subject
        FROM subjects
        WHERE book.subject_id = subjects.id
        """
    )
    op.execute("UPDATE book SET subject = 'UNKNOWN'::subject WHERE subject IS NULL")
    op.alter_column(
        "book",
        "subject",
        existing_type=postgresql.ENUM(name="subject", create_type=False),
        nullable=False,
    )
