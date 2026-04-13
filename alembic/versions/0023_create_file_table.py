"""create file table

Revision ID: 0023_create_file_table
Revises: 0022_add_name_column_to_class
Create Date: 2026-04-10 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM

# revision identifiers, used by Alembic.
revision: str = '0023_create_file_table'
down_revision: Union[str, Sequence[str], None] = '0022_add_name_column_to_class'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("DO $$ BEGIN CREATE TYPE file_bucket AS ENUM ('PUBLIC', 'PRIVATE'); EXCEPTION WHEN duplicate_object THEN NULL; END $$")

    op.create_table(
        'file',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('content_type', sa.String(), nullable=False),
        sa.Column('size_bytes', sa.Integer(), nullable=False),
        sa.Column('bucket', ENUM('PUBLIC', 'PRIVATE', name='file_bucket', create_type=False), nullable=False),
        sa.Column('object_key', sa.String(), nullable=False),
        sa.Column('lesplan_request_id', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.ForeignKeyConstraint(['lesplan_request_id'], ['lesplan_request.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('object_key'),
    )
    op.create_index('ix_file_user_id', 'file', ['user_id'])
    op.create_index('ix_file_lesplan_request_id', 'file', ['lesplan_request_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_file_lesplan_request_id', table_name='file')
    op.drop_index('ix_file_user_id', table_name='file')
    op.drop_table('file')

    sa.Enum(name='file_bucket').drop(op.get_bind(), checkfirst=True)
