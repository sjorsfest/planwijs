from datetime import date
from sqlmodel import SQLModel
from app.models.base import BaseModel


class EventBase(SQLModel):
    name: str
    description: str | None = None
    planned_date: date


class EventCreate(EventBase):
    pass


class Event(EventBase, BaseModel, table=True):
    pass
