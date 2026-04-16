from typing import Optional

from sqlalchemy import Column, ForeignKey, String, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlmodel import Field

from app.models.base import BaseModel
from app.models.enums import OrganizationRole


class OrganizationMembership(BaseModel, table=True):
    __tablename__ = "organization_membership"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_organization_membership_user_id"),
    )

    user_id: str = Field(
        sa_column=Column(
            String,
            ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
            index=True,
        )
    )
    organization_id: str = Field(
        sa_column=Column(
            String,
            ForeignKey("organization.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    role: OrganizationRole = Field(
        default=OrganizationRole.MEMBER,
        sa_column=Column(
            SAEnum(OrganizationRole, name="organization_role", create_type=False),
            nullable=False,
        ),
    )
