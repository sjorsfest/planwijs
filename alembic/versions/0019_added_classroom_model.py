"""added classroom model

Revision ID: 0019_added_classroom_model
Revises: 0018_add_event_user_id
Create Date: 2026-04-09 11:48:40.397458

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0019_added_classroom_model'
down_revision: Union[str, Sequence[str], None] = '0018_add_event_user_id'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('classroom',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('assets', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_classroom_user_id'), 'classroom', ['user_id'], unique=False)

    op.drop_index(op.f('ix_event_user_id'), table_name='event')
    op.drop_table('event')


def downgrade() -> None:
    """Downgrade schema."""
    op.create_table('event',
        sa.Column('id', sa.VARCHAR(), nullable=False),
        sa.Column('created_at', postgresql.TIMESTAMP(), nullable=False),
        sa.Column('updated_at', postgresql.TIMESTAMP(), nullable=False),
        sa.Column('name', sa.VARCHAR(), nullable=False),
        sa.Column('description', sa.VARCHAR(), nullable=True),
        sa.Column('planned_date', sa.DATE(), nullable=False),
        sa.Column('user_id', sa.VARCHAR(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], name=op.f('fk_event_user_id')),
        sa.PrimaryKeyConstraint('id', name=op.f('event_pkey')),
    )
    op.create_index(op.f('ix_event_user_id'), 'event', ['user_id'], unique=False)

    op.drop_index(op.f('ix_classroom_user_id'), table_name='classroom')
    op.drop_table('classroom')
