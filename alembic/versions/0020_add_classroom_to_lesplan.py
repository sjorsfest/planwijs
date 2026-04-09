"""add classroom_id to lesplan_request

Revision ID: 0020_add_classroom_to_lesplan
Revises: 0019_added_classroom_model
Create Date: 2026-04-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0020_add_classroom_to_lesplan'
down_revision: Union[str, Sequence[str], None] = '0019_added_classroom_model'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('lesplan_request', sa.Column('classroom_id', sa.String(), nullable=True))
    op.create_index(op.f('ix_lesplan_request_classroom_id'), 'lesplan_request', ['classroom_id'], unique=False)
    op.create_foreign_key(
        'fk_lesplan_request_classroom_id',
        'lesplan_request', 'classroom',
        ['classroom_id'], ['id'],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('fk_lesplan_request_classroom_id', 'lesplan_request', type_='foreignkey')
    op.drop_index(op.f('ix_lesplan_request_classroom_id'), table_name='lesplan_request')
    op.drop_column('lesplan_request', 'classroom_id')
