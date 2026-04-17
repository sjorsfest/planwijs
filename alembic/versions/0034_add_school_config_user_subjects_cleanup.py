"""add school_config and user_subject tables, drop subject and support_challenge from class

Revision ID: 0034_school_config_user_subjects
Revises: 0033_add_test_feedback
Create Date: 2026-04-17 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM, JSONB

# revision identifiers, used by Alembic.
revision: str = "0034_school_config_user_subjects"
down_revision: Union[str, None] = "0033_add_test_feedback"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Create school_type enum ---
    op.execute(
        "DO $$ BEGIN "
        "CREATE TYPE school_type AS ENUM "
        "('REGULIER', 'MONTESSORI', 'DALTON', 'JENAPLAN', "
        "'VRIJE_SCHOOL', 'TECHNASIUM', 'TWEETALIG', 'ANDERS'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
    )

    # --- Create school_config table ---
    op.create_table(
        "school_config",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column(
            "organization_id",
            sa.String(),
            sa.ForeignKey("organization.id", ondelete="CASCADE"),
            nullable=True,
            unique=True,
            index=True,
        ),
        sa.Column(
            "user_id",
            sa.String(),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=True,
            unique=True,
            index=True,
        ),
        sa.Column("default_lesson_duration_minutes", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("levels", JSONB, nullable=False, server_default="[]"),
        sa.Column(
            "school_type",
            ENUM(
                "REGULIER", "MONTESSORI", "DALTON", "JENAPLAN",
                "VRIJE_SCHOOL", "TECHNASIUM", "TWEETALIG", "ANDERS",
                name="school_type",
                create_type=False,
            ),
            nullable=True,
        ),
        sa.Column("context_notes", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "(organization_id IS NOT NULL AND user_id IS NULL) OR "
            "(organization_id IS NULL AND user_id IS NOT NULL)",
            name="ck_school_config_exactly_one_owner",
        ),
    )

    # --- Create user_subject table ---
    op.create_table(
        "user_subject",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column(
            "user_id",
            sa.String(),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "subject_id",
            sa.String(),
            sa.ForeignKey("subjects.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "subject_id", name="uq_user_subject"),
    )

    # --- Drop support_challenge column from class ---
    op.drop_column("class", "support_challenge")

    # --- Drop subject column from class ---
    op.drop_column("class", "subject")

    # --- Drop the class_support_challenge enum type ---
    op.execute("DROP TYPE IF EXISTS class_support_challenge")


def downgrade() -> None:
    # --- Re-create enums ---
    class_support_challenge = sa.Enum(
        "MORE_SUPPORT", "BALANCED", "MORE_CHALLENGE",
        name="class_support_challenge",
    )
    class_support_challenge.create(op.get_bind(), checkfirst=True)

    # --- Re-add columns ---
    op.add_column(
        "class",
        sa.Column(
            "subject",
            sa.Enum(
                "Aardrijkskunde", "Bedrijfseconomie", "Biologie", "Duits", "Economie",
                "Engels", "Frans", "Geschiedenis", "Grieks", "Latijn",
                "Levens beschouwing", "Maatschappijleer", "MAW", "Mens & Maatschappij",
                "Nask/Science", "Natuurkunde", "Nederlands", "Scheikunde", "Spaans",
                "Wiskunde", "Wiskunde A", "Wiskunde B", "Unknown",
                name="subject",
                create_type=False,
            ),
            nullable=False,
            server_default="Unknown",
        ),
    )
    op.add_column(
        "class",
        sa.Column(
            "support_challenge",
            class_support_challenge,
            nullable=True,
        ),
    )

    # --- Drop new tables ---
    op.drop_table("user_subject")
    op.drop_table("school_config")

    # --- Drop school_type enum ---
    op.execute("DROP TYPE IF EXISTS school_type")
