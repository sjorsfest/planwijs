from sqlalchemy import Column, ForeignKey, String
from sqlalchemy import Enum as SAEnum
from sqlmodel import Field

from app.models.base import BaseModel
from app.models.enums import InviteStatus, OrganizationRole


class OrganizationInvite(BaseModel, table=True):
    __tablename__ = "organization_invite"

    organization_id: str = Field(
        sa_column=Column(
            String,
            ForeignKey("organization.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    email: str = Field(index=True)
    role: OrganizationRole = Field(
        default=OrganizationRole.MEMBER,
        sa_column=Column(
            SAEnum(OrganizationRole, name="organization_role", create_type=False),
            nullable=False,
        ),
    )
    invited_by_user_id: str = Field(
        sa_column=Column(
            String,
            ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    status: InviteStatus = Field(
        default=InviteStatus.PENDING,
        sa_column=Column(
            SAEnum(InviteStatus, name="invite_status", create_type=False),
            nullable=False,
            server_default="PENDING",
        ),
    )
