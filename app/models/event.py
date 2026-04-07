from datetime import date

from sqlmodel import Field, SQLModel

from app.models.base import BaseModel


class EventBase(SQLModel):
    name: str
    description: str | None = None
    planned_date: date


class EventCreate(EventBase):
    pass


class Event(EventBase, BaseModel, table=True):
    user_id: str = Field(foreign_key="user.id", index=True)
