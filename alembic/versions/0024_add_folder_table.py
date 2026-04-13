"""add folder table and file folder_id

Revision ID: 0024_add_folder_table
Revises: 0023_create_file_table
Create Date: 2026-04-13 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0024_add_folder_table'
down_revision: Union[str, Sequence[str], None] = '0023_create_file_table'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'folder',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('parent_id', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.ForeignKeyConstraint(['parent_id'], ['folder.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_folder_user_id', 'folder', ['user_id'])
    op.create_index('ix_folder_parent_id', 'folder', ['parent_id'])

    op.add_column('file', sa.Column('folder_id', sa.String(), nullable=True))
    op.create_foreign_key('fk_file_folder_id', 'file', 'folder', ['folder_id'], ['id'])
    op.create_index('ix_file_folder_id', 'file', ['folder_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_file_folder_id', table_name='file')
    op.drop_constraint('fk_file_folder_id', 'file', type_='foreignkey')
    op.drop_column('file', 'folder_id')

    op.drop_index('ix_folder_parent_id', table_name='folder')
    op.drop_index('ix_folder_user_id', table_name='folder')
    op.drop_table('folder')
