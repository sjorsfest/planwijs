"""add extracted_text and status columns to file table

Revision ID: 0025_add_extracted_text
Revises: 0024_add_folder_table
Create Date: 2026-04-13 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM


# revision identifiers, used by Alembic.
revision: str = "0025_add_extracted_text"
down_revision: Union[str, None] = "0024_add_folder_table"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "DO $$ BEGIN CREATE TYPE file_status AS ENUM ('PENDING', 'UPLOADED', 'FAILED'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
    )
    op.add_column("file", sa.Column("extracted_text", sa.Text(), nullable=True))
    op.add_column(
        "file",
        sa.Column(
            "status",
            ENUM("PENDING", "UPLOADED", "FAILED", name="file_status", create_type=False),
            nullable=False,
            server_default="PENDING",
        ),
    )


def downgrade() -> None:
    op.drop_column("file", "status")
    op.drop_column("file", "extracted_text")
    sa.Enum(name="file_status").drop(op.get_bind(), checkfirst=True)
