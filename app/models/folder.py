from typing import Optional

from sqlalchemy import Column, ForeignKey, String
from sqlmodel import Field

from app.models.base import BaseModel


class Folder(BaseModel, table=True):
    __tablename__ = "folder"  # type: ignore[assignment]

    user_id: str = Field(
        sa_column=Column(String, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    )
    name: str
    parent_id: Optional[str] = Field(
        default=None,
        sa_column=Column(String, ForeignKey("folder.id", ondelete="SET NULL"), nullable=True, index=True),
    )
    organization_id: Optional[str] = Field(
        default=None,
        sa_column=Column(String, ForeignKey("organization.id", ondelete="SET NULL"), nullable=True, index=True),
    )
