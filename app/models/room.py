from typing import List

from sqlalchemy import Column
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
    user_id: str = Field(foreign_key="user.id", index=True)
