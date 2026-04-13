"""add status column to file table

Revision ID: 0026_add_status_for_files
Revises: 0025_add_extracted_text
Create Date: 2026-04-13 15:54:53.095888

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM


# revision identifiers, used by Alembic.
revision: str = "0026_add_status_for_files"
down_revision: Union[str, Sequence[str], None] = "0025_add_extracted_text"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "DO $$ BEGIN CREATE TYPE file_status AS ENUM ('PENDING', 'UPLOADED', 'FAILED'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
    )
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
    sa.Enum(name="file_status").drop(op.get_bind(), checkfirst=True)
