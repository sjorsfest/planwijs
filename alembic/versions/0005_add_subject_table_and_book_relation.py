"""add subject table and relation to books

Revision ID: 0005_add_subject_book_relation
Revises: 0004_class_difficulty_nullable
Create Date: 2026-03-26 15:00:00.000000

"""

from datetime import datetime
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from cuid2 import Cuid
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_add_subject_book_relation"
down_revision: Union[str, Sequence[str], None] = "0004_class_difficulty_nullable"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SUBJECT_CATEGORY_VALUES = (
    "TALEN",
    "EXACTE_VAKKEN",
    "MENS_EN_MAATSCHAPPIJ",
    "ECONOMIE",
)

_SUBJECT_ROWS = (
    ("nederlands", "Nederlands", "TALEN", "NEDERLANDS"),
    ("engels", "Engels", "TALEN", "ENGELS"),
    ("duits", "Duits", "TALEN", "DUITS"),
    ("frans", "Frans", "TALEN", "FRANS"),
    ("spaans", "Spaans", "TALEN", "SPAANS"),
    ("grieks", "Grieks", "TALEN", "GRIEKS"),
    ("latijn", "Latijn", "TALEN", "LATIJN"),
    ("wiskunde", "Wiskunde", "EXACTE_VAKKEN", "WISKUNDE"),
    ("wiskunde-a", "Wiskunde A", "EXACTE_VAKKEN", "WISKUNDE_A"),
    ("wiskunde-b", "Wiskunde B", "EXACTE_VAKKEN", "WISKUNDE_B"),
    ("natuurkunde", "Natuurkunde", "EXACTE_VAKKEN", "NATUURKUNDE"),
    ("scheikunde", "Scheikunde", "EXACTE_VAKKEN", "SCHEIKUNDE"),
    ("biologie", "Biologie", "EXACTE_VAKKEN", "BIOLOGIE"),
    ("nask-science", "Nask/Science", "EXACTE_VAKKEN", "NASK_SCIENCE"),
    ("aardrijkskunde", "Aardrijkskunde", "MENS_EN_MAATSCHAPPIJ", "AARDRIJKSKUNDE"),
    ("geschiedenis", "Geschiedenis", "MENS_EN_MAATSCHAPPIJ", "GESCHIEDENIS"),
    ("maatschappijleer", "Maatschappijleer", "MENS_EN_MAATSCHAPPIJ", "MAATSCHAPPIJLEER"),
    ("maw", "MAW", "MENS_EN_MAATSCHAPPIJ", "MAW"),
    (
        "mens-en-maatschappij",
        "Mens & Maatschappij",
        "MENS_EN_MAATSCHAPPIJ",
        "MENS_EN_MAATSCHAPPIJ",
    ),
    (
        "levensbeschouwing",
        "Levensbeschouwing",
        "MENS_EN_MAATSCHAPPIJ",
        "LEVENS_BESCHOUWING",
    ),
    ("economie", "Economie", "ECONOMIE", "ECONOMIE"),
    ("bedrijfseconomie", "Bedrijfseconomie", "ECONOMIE", "BEDRIJFSECONOMIE"),
)


def upgrade() -> None:
    values = ", ".join(f"'{v}'" for v in _SUBJECT_CATEGORY_VALUES)
    op.execute(f"CREATE TYPE subject_category AS ENUM ({values})")

    op.create_table(
        "subjects",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("slug", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("category", postgresql.ENUM(name="subject_category", create_type=False), nullable=False),
        sa.Column("legacy_subject", postgresql.ENUM(name="subject", create_type=False), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
        sa.UniqueConstraint("name"),
        sa.UniqueConstraint("legacy_subject"),
    )
    op.create_index(op.f("ix_subjects_slug"), "subjects", ["slug"], unique=True)

    now = datetime.utcnow()
    cuid = Cuid()
    subject_table = sa.table(
        "subjects",
        sa.column("id", sqlmodel.sql.sqltypes.AutoString()),
        sa.column("created_at", sa.DateTime()),
        sa.column("updated_at", sa.DateTime()),
        sa.column("slug", sqlmodel.sql.sqltypes.AutoString()),
        sa.column("name", sqlmodel.sql.sqltypes.AutoString()),
        sa.column("category", postgresql.ENUM(name="subject_category", create_type=False)),
        sa.column("legacy_subject", postgresql.ENUM(name="subject", create_type=False)),
    )
    op.bulk_insert(
        subject_table,
        [
            {
                "id": cuid.generate(),
                "created_at": now,
                "updated_at": now,
                "slug": slug,
                "name": name,
                "category": category,
                "legacy_subject": legacy_subject,
            }
            for slug, name, category, legacy_subject in _SUBJECT_ROWS
        ],
    )

    op.add_column("book", sa.Column("subject_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.create_index(op.f("ix_book_subject_id"), "book", ["subject_id"], unique=False)
    op.create_foreign_key(
        "fk_book_subject_id_subject",
        "book",
        "subjects",
        ["subject_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.execute(
        """
        UPDATE book
        SET subject_id = subjects.id
        FROM subjects
        WHERE book.subject = subjects.legacy_subject
        """
    )


def downgrade() -> None:
    op.drop_constraint("fk_book_subject_id_subject", "book", type_="foreignkey")
    op.drop_index(op.f("ix_book_subject_id"), table_name="book")
    op.drop_column("book", "subject_id")

    op.drop_index(op.f("ix_subjects_slug"), table_name="subjects")
    op.drop_table("subjects")
    op.execute("DROP TYPE subject_category")
