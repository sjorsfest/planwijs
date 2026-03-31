"""fix lesson_preparation_status enum labels to uppercase

Revision ID: 0016_fix_preparation_status
Revises: 0015_review_overview_contract
Create Date: 2026-03-31 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

revision: str = "0016_fix_preparation_status"
down_revision: Union[str, Sequence[str], None] = "0015_review_overview_contract"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'lesson_preparation_status') THEN
                IF EXISTS (
                    SELECT 1
                    FROM pg_type t
                    JOIN pg_enum e ON e.enumtypid = t.oid
                    WHERE t.typname = 'lesson_preparation_status' AND e.enumlabel = 'pending'
                ) AND NOT EXISTS (
                    SELECT 1
                    FROM pg_type t
                    JOIN pg_enum e ON e.enumtypid = t.oid
                    WHERE t.typname = 'lesson_preparation_status' AND e.enumlabel = 'PENDING'
                ) THEN
                    ALTER TYPE lesson_preparation_status RENAME VALUE 'pending' TO 'PENDING';
                END IF;

                IF EXISTS (
                    SELECT 1
                    FROM pg_type t
                    JOIN pg_enum e ON e.enumtypid = t.oid
                    WHERE t.typname = 'lesson_preparation_status' AND e.enumlabel = 'done'
                ) AND NOT EXISTS (
                    SELECT 1
                    FROM pg_type t
                    JOIN pg_enum e ON e.enumtypid = t.oid
                    WHERE t.typname = 'lesson_preparation_status' AND e.enumlabel = 'DONE'
                ) THEN
                    ALTER TYPE lesson_preparation_status RENAME VALUE 'done' TO 'DONE';
                END IF;
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'lesson_preparation_status') THEN
                IF EXISTS (
                    SELECT 1
                    FROM pg_type t
                    JOIN pg_enum e ON e.enumtypid = t.oid
                    WHERE t.typname = 'lesson_preparation_status' AND e.enumlabel = 'PENDING'
                ) AND NOT EXISTS (
                    SELECT 1
                    FROM pg_type t
                    JOIN pg_enum e ON e.enumtypid = t.oid
                    WHERE t.typname = 'lesson_preparation_status' AND e.enumlabel = 'pending'
                ) THEN
                    ALTER TYPE lesson_preparation_status RENAME VALUE 'PENDING' TO 'pending';
                END IF;

                IF EXISTS (
                    SELECT 1
                    FROM pg_type t
                    JOIN pg_enum e ON e.enumtypid = t.oid
                    WHERE t.typname = 'lesson_preparation_status' AND e.enumlabel = 'DONE'
                ) AND NOT EXISTS (
                    SELECT 1
                    FROM pg_type t
                    JOIN pg_enum e ON e.enumtypid = t.oid
                    WHERE t.typname = 'lesson_preparation_status' AND e.enumlabel = 'done'
                ) THEN
                    ALTER TYPE lesson_preparation_status RENAME VALUE 'DONE' TO 'done';
                END IF;
            END IF;
        END
        $$;
        """
    )
