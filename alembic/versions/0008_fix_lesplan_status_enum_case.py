"""fix lesplan_status enum labels to uppercase

Revision ID: 0008_lesplan_status_case
Revises: 0007_add_lesplan_tables
Create Date: 2026-03-26 19:10:00.000000

"""

from typing import Sequence, Union

from alembic import op

revision: str = "0008_lesplan_status_case"
down_revision: Union[str, Sequence[str], None] = "0007_add_lesplan_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'lesplan_status') THEN
                IF EXISTS (
                    SELECT 1
                    FROM pg_type t
                    JOIN pg_enum e ON e.enumtypid = t.oid
                    WHERE t.typname = 'lesplan_status' AND e.enumlabel = 'pending'
                ) AND NOT EXISTS (
                    SELECT 1
                    FROM pg_type t
                    JOIN pg_enum e ON e.enumtypid = t.oid
                    WHERE t.typname = 'lesplan_status' AND e.enumlabel = 'PENDING'
                ) THEN
                    ALTER TYPE lesplan_status RENAME VALUE 'pending' TO 'PENDING';
                END IF;

                IF EXISTS (
                    SELECT 1
                    FROM pg_type t
                    JOIN pg_enum e ON e.enumtypid = t.oid
                    WHERE t.typname = 'lesplan_status' AND e.enumlabel = 'generating_overview'
                ) AND NOT EXISTS (
                    SELECT 1
                    FROM pg_type t
                    JOIN pg_enum e ON e.enumtypid = t.oid
                    WHERE t.typname = 'lesplan_status' AND e.enumlabel = 'GENERATING_OVERVIEW'
                ) THEN
                    ALTER TYPE lesplan_status RENAME VALUE 'generating_overview' TO 'GENERATING_OVERVIEW';
                END IF;

                IF EXISTS (
                    SELECT 1
                    FROM pg_type t
                    JOIN pg_enum e ON e.enumtypid = t.oid
                    WHERE t.typname = 'lesplan_status' AND e.enumlabel = 'overview_ready'
                ) AND NOT EXISTS (
                    SELECT 1
                    FROM pg_type t
                    JOIN pg_enum e ON e.enumtypid = t.oid
                    WHERE t.typname = 'lesplan_status' AND e.enumlabel = 'OVERVIEW_READY'
                ) THEN
                    ALTER TYPE lesplan_status RENAME VALUE 'overview_ready' TO 'OVERVIEW_READY';
                END IF;

                IF EXISTS (
                    SELECT 1
                    FROM pg_type t
                    JOIN pg_enum e ON e.enumtypid = t.oid
                    WHERE t.typname = 'lesplan_status' AND e.enumlabel = 'revising_overview'
                ) AND NOT EXISTS (
                    SELECT 1
                    FROM pg_type t
                    JOIN pg_enum e ON e.enumtypid = t.oid
                    WHERE t.typname = 'lesplan_status' AND e.enumlabel = 'REVISING_OVERVIEW'
                ) THEN
                    ALTER TYPE lesplan_status RENAME VALUE 'revising_overview' TO 'REVISING_OVERVIEW';
                END IF;

                IF EXISTS (
                    SELECT 1
                    FROM pg_type t
                    JOIN pg_enum e ON e.enumtypid = t.oid
                    WHERE t.typname = 'lesplan_status' AND e.enumlabel = 'generating_lessons'
                ) AND NOT EXISTS (
                    SELECT 1
                    FROM pg_type t
                    JOIN pg_enum e ON e.enumtypid = t.oid
                    WHERE t.typname = 'lesplan_status' AND e.enumlabel = 'GENERATING_LESSONS'
                ) THEN
                    ALTER TYPE lesplan_status RENAME VALUE 'generating_lessons' TO 'GENERATING_LESSONS';
                END IF;

                IF EXISTS (
                    SELECT 1
                    FROM pg_type t
                    JOIN pg_enum e ON e.enumtypid = t.oid
                    WHERE t.typname = 'lesplan_status' AND e.enumlabel = 'completed'
                ) AND NOT EXISTS (
                    SELECT 1
                    FROM pg_type t
                    JOIN pg_enum e ON e.enumtypid = t.oid
                    WHERE t.typname = 'lesplan_status' AND e.enumlabel = 'COMPLETED'
                ) THEN
                    ALTER TYPE lesplan_status RENAME VALUE 'completed' TO 'COMPLETED';
                END IF;

                IF EXISTS (
                    SELECT 1
                    FROM pg_type t
                    JOIN pg_enum e ON e.enumtypid = t.oid
                    WHERE t.typname = 'lesplan_status' AND e.enumlabel = 'failed'
                ) AND NOT EXISTS (
                    SELECT 1
                    FROM pg_type t
                    JOIN pg_enum e ON e.enumtypid = t.oid
                    WHERE t.typname = 'lesplan_status' AND e.enumlabel = 'FAILED'
                ) THEN
                    ALTER TYPE lesplan_status RENAME VALUE 'failed' TO 'FAILED';
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
            IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'lesplan_status') THEN
                IF EXISTS (
                    SELECT 1
                    FROM pg_type t
                    JOIN pg_enum e ON e.enumtypid = t.oid
                    WHERE t.typname = 'lesplan_status' AND e.enumlabel = 'PENDING'
                ) AND NOT EXISTS (
                    SELECT 1
                    FROM pg_type t
                    JOIN pg_enum e ON e.enumtypid = t.oid
                    WHERE t.typname = 'lesplan_status' AND e.enumlabel = 'pending'
                ) THEN
                    ALTER TYPE lesplan_status RENAME VALUE 'PENDING' TO 'pending';
                END IF;

                IF EXISTS (
                    SELECT 1
                    FROM pg_type t
                    JOIN pg_enum e ON e.enumtypid = t.oid
                    WHERE t.typname = 'lesplan_status' AND e.enumlabel = 'GENERATING_OVERVIEW'
                ) AND NOT EXISTS (
                    SELECT 1
                    FROM pg_type t
                    JOIN pg_enum e ON e.enumtypid = t.oid
                    WHERE t.typname = 'lesplan_status' AND e.enumlabel = 'generating_overview'
                ) THEN
                    ALTER TYPE lesplan_status RENAME VALUE 'GENERATING_OVERVIEW' TO 'generating_overview';
                END IF;

                IF EXISTS (
                    SELECT 1
                    FROM pg_type t
                    JOIN pg_enum e ON e.enumtypid = t.oid
                    WHERE t.typname = 'lesplan_status' AND e.enumlabel = 'OVERVIEW_READY'
                ) AND NOT EXISTS (
                    SELECT 1
                    FROM pg_type t
                    JOIN pg_enum e ON e.enumtypid = t.oid
                    WHERE t.typname = 'lesplan_status' AND e.enumlabel = 'overview_ready'
                ) THEN
                    ALTER TYPE lesplan_status RENAME VALUE 'OVERVIEW_READY' TO 'overview_ready';
                END IF;

                IF EXISTS (
                    SELECT 1
                    FROM pg_type t
                    JOIN pg_enum e ON e.enumtypid = t.oid
                    WHERE t.typname = 'lesplan_status' AND e.enumlabel = 'REVISING_OVERVIEW'
                ) AND NOT EXISTS (
                    SELECT 1
                    FROM pg_type t
                    JOIN pg_enum e ON e.enumtypid = t.oid
                    WHERE t.typname = 'lesplan_status' AND e.enumlabel = 'revising_overview'
                ) THEN
                    ALTER TYPE lesplan_status RENAME VALUE 'REVISING_OVERVIEW' TO 'revising_overview';
                END IF;

                IF EXISTS (
                    SELECT 1
                    FROM pg_type t
                    JOIN pg_enum e ON e.enumtypid = t.oid
                    WHERE t.typname = 'lesplan_status' AND e.enumlabel = 'GENERATING_LESSONS'
                ) AND NOT EXISTS (
                    SELECT 1
                    FROM pg_type t
                    JOIN pg_enum e ON e.enumtypid = t.oid
                    WHERE t.typname = 'lesplan_status' AND e.enumlabel = 'generating_lessons'
                ) THEN
                    ALTER TYPE lesplan_status RENAME VALUE 'GENERATING_LESSONS' TO 'generating_lessons';
                END IF;

                IF EXISTS (
                    SELECT 1
                    FROM pg_type t
                    JOIN pg_enum e ON e.enumtypid = t.oid
                    WHERE t.typname = 'lesplan_status' AND e.enumlabel = 'COMPLETED'
                ) AND NOT EXISTS (
                    SELECT 1
                    FROM pg_type t
                    JOIN pg_enum e ON e.enumtypid = t.oid
                    WHERE t.typname = 'lesplan_status' AND e.enumlabel = 'completed'
                ) THEN
                    ALTER TYPE lesplan_status RENAME VALUE 'COMPLETED' TO 'completed';
                END IF;

                IF EXISTS (
                    SELECT 1
                    FROM pg_type t
                    JOIN pg_enum e ON e.enumtypid = t.oid
                    WHERE t.typname = 'lesplan_status' AND e.enumlabel = 'FAILED'
                ) AND NOT EXISTS (
                    SELECT 1
                    FROM pg_type t
                    JOIN pg_enum e ON e.enumtypid = t.oid
                    WHERE t.typname = 'lesplan_status' AND e.enumlabel = 'failed'
                ) THEN
                    ALTER TYPE lesplan_status RENAME VALUE 'FAILED' TO 'failed';
                END IF;
            END IF;
        END
        $$;
        """
    )
