from typing import List, Optional

from sqlalchemy import Column, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from app.models.base import BaseModel


class ClassroomBase(SQLModel):
    name: str
    description: str | None = None
    assets: List[str] = Field(
        default_factory=list,
        sa_column=Column("assets", JSONB, nullable=False, server_default="[]"),
        description="Beschikbare middelen in het lokaal (bijv. Digibord, Whiteboard, Lab-materiaal).",
    )


class ClassroomCreate(ClassroomBase):
    pass


class Classroom(ClassroomBase, BaseModel, table=True):
    user_id: str = Field(
        sa_column=Column(String, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    )
    organization_id: Optional[str] = Field(
        default=None,
        sa_column=Column(String, ForeignKey("organization.id", ondelete="SET NULL"), nullable=True, index=True),
    )
