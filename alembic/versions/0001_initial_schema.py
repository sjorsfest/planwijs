"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-03-24 16:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0001_initial_schema'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SUBJECT_VALUES = (
    'AARDRIJKSKUNDE', 'BEDRIJFSECONOMIE', 'BIOLOGIE', 'DUITS', 'ECONOMIE',
    'ENGELS', 'FRANS', 'GESCHIEDENIS', 'GRIEKS', 'LATIJN', 'LEVENS_BESCHOUWING',
    'MAATSCHAPPIJLEER', 'MAW', 'MENS_EN_MAATSCHAPPIJ', 'NASK_SCIENCE',
    'NATUURKUNDE', 'NEDERLANDS', 'SCHEIKUNDE', 'SPAANS', 'WISKUNDE',
    'WISKUNDE_A', 'WISKUNDE_B', 'UNKNOWN',
)


def upgrade() -> None:
    values = ", ".join(f"'{v}'" for v in _SUBJECT_VALUES)
    op.execute(f"CREATE TYPE subject AS ENUM ({values})")

    op.create_table(
        'user',
        sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('name', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('email', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('google_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email'),
        sa.UniqueConstraint('google_id'),
    )

    op.create_table(
        'event',
        sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('name', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('description', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('planned_date', sa.Date(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'method',
        sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('slug', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('title', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('subject', postgresql.ENUM(name='subject', create_type=False), nullable=False),
        sa.Column('url', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_method_slug'), 'method', ['slug'], unique=True)

    op.create_table(
        'book',
        sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('book_id', sa.Integer(), nullable=True),
        sa.Column('slug', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('title', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('subject', postgresql.ENUM(name='subject', create_type=False), nullable=False),
        sa.Column('method_id', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('edition', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('school_years', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        sa.Column('levels', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        sa.Column('cover_url', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('url', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.ForeignKeyConstraint(['method_id'], ['method.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('url'),
    )
    op.create_index(op.f('ix_book_slug'), 'book', ['slug'], unique=False)

    op.create_table(
        'book_chapter',
        sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('index', sa.Integer(), nullable=False),
        sa.Column('title', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('toets_url', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('book_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.ForeignKeyConstraint(['book_id'], ['book.id']),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('book_chapter')
    op.drop_index(op.f('ix_book_slug'), table_name='book')
    op.drop_table('book')
    op.drop_index(op.f('ix_method_slug'), table_name='method')
    op.drop_table('method')
    op.drop_table('event')
    op.drop_table('user')
    op.execute("DROP TYPE subject")
