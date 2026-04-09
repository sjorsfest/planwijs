"""drop approval_readiness from lesplan_overview

Revision ID: 0021_drop_approval_readiness
Revises: 0020_add_classroom_to_lesplan
Create Date: 2026-04-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = '0021_drop_approval_readiness'
down_revision: Union[str, Sequence[str], None] = '0020_add_classroom_to_lesplan'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column('lesplan_overview', 'approval_readiness')


def downgrade() -> None:
    op.add_column(
        'lesplan_overview',
        sa.Column('approval_readiness', JSONB, nullable=False, server_default='{}'),
    )
