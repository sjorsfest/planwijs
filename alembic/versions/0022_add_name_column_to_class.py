"""add name column to class table

Revision ID: 0022_add_name_column_to_class
Revises: 0021_drop_approval_readiness
Create Date: 2026-04-09 17:09:35.808839

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0022_add_name_column_to_class'
down_revision: Union[str, Sequence[str], None] = '0021_drop_approval_readiness'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('class', sa.Column('name', sa.String(), nullable=False, server_default=''))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('class', 'name')
