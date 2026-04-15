"""add organizations, memberships, invites, and organization_id to resources

Revision ID: 0031_add_organizations
Revises: 0030_add_class_id_to_file
Create Date: 2026-04-15 14:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM

# revision identifiers, used by Alembic.
revision: str = "0031_add_organizations"
down_revision: Union[str, Sequence[str], None] = "0030_add_class_id_to_file"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    # --- Clean up any leftovers from a previously failed run ---
    # Drop tables in reverse dependency order (safe if they don't exist)
    for tbl in ("organization_invite", "organization_membership", "organization"):
        bind.execute(sa.text(f"DROP TABLE IF EXISTS {tbl} CASCADE"))

    # Drop enum types that may have been created in a failed run
    for enum_name in ("invite_status", "organization_role", "user_role"):
        bind.execute(sa.text(f"DROP TYPE IF EXISTS {enum_name}"))

    # Drop user_role column if it was partially added
    bind.execute(sa.text(
        "ALTER TABLE \"user\" DROP COLUMN IF EXISTS user_role"
    ))

    # Drop organization_id columns from resource tables if partially added
    for table in ("class", "classroom", "file", "folder", "lesplan_request"):
        bind.execute(sa.text(f'ALTER TABLE "{table}" DROP COLUMN IF EXISTS organization_id'))

    # --- Enum types ---
    sa.Enum("USER", "ADMIN", name="user_role").create(bind)
    sa.Enum("ADMIN", "MEMBER", name="organization_role").create(bind)
    sa.Enum("PENDING", "ACCEPTED", "DECLINED", name="invite_status").create(bind)

    # --- User: add user_role ---
    op.add_column(
        "user",
        sa.Column("user_role", ENUM("USER", "ADMIN", name="user_role", create_type=False), nullable=False, server_default="USER"),
    )

    # --- Organization table ---
    op.create_table(
        "organization",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.UniqueConstraint("slug", name="uq_organization_slug"),
    )
    op.create_index(op.f("ix_organization_slug"), "organization", ["slug"], unique=True)

    # --- OrganizationMembership table ---
    op.create_table(
        "organization_membership",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("organization_id", sa.String(), nullable=False),
        sa.Column("role", ENUM("ADMIN", "MEMBER", name="organization_role", create_type=False), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organization.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", name="uq_organization_membership_user_id"),
    )
    op.create_index(op.f("ix_organization_membership_user_id"), "organization_membership", ["user_id"], unique=True)
    op.create_index(op.f("ix_organization_membership_organization_id"), "organization_membership", ["organization_id"], unique=False)

    # --- OrganizationInvite table ---
    op.create_table(
        "organization_invite",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("organization_id", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("role", ENUM("ADMIN", "MEMBER", name="organization_role", create_type=False), nullable=False),
        sa.Column("invited_by_user_id", sa.String(), nullable=False),
        sa.Column("status", ENUM("PENDING", "ACCEPTED", "DECLINED", name="invite_status", create_type=False), nullable=False, server_default="PENDING"),
        sa.ForeignKeyConstraint(["organization_id"], ["organization.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["invited_by_user_id"], ["user.id"], ondelete="CASCADE"),
    )
    op.create_index(op.f("ix_organization_invite_organization_id"), "organization_invite", ["organization_id"], unique=False)
    op.create_index(op.f("ix_organization_invite_email"), "organization_invite", ["email"], unique=False)

    # --- Add organization_id to resource tables ---
    for table in ("class", "classroom", "file", "folder", "lesplan_request"):
        op.add_column(table, sa.Column("organization_id", sa.String(), nullable=True))
        op.create_index(op.f(f"ix_{table}_organization_id"), table, ["organization_id"], unique=False)
        op.create_foreign_key(
            f"{table}_organization_id_fkey",
            table,
            "organization",
            ["organization_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    # --- Remove organization_id from resource tables ---
    for table in ("class", "classroom", "file", "folder", "lesplan_request"):
        op.drop_constraint(f"{table}_organization_id_fkey", table, type_="foreignkey")
        op.drop_index(op.f(f"ix_{table}_organization_id"), table_name=table)
        op.drop_column(table, "organization_id")

    # --- Drop tables ---
    op.drop_index(op.f("ix_organization_invite_email"), table_name="organization_invite")
    op.drop_index(op.f("ix_organization_invite_organization_id"), table_name="organization_invite")
    op.drop_table("organization_invite")

    op.drop_index(op.f("ix_organization_membership_organization_id"), table_name="organization_membership")
    op.drop_index(op.f("ix_organization_membership_user_id"), table_name="organization_membership")
    op.drop_table("organization_membership")

    op.drop_index(op.f("ix_organization_slug"), table_name="organization")
    op.drop_table("organization")

    # --- Drop user_role column ---
    op.drop_column("user", "user_role")

    # --- Drop enum types ---
    sa.Enum(name="invite_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="organization_role").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="user_role").drop(op.get_bind(), checkfirst=True)
