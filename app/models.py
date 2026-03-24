from datetime import date
from cuid2 import Cuid
from sqlmodel import Field, SQLModel

_cuid = Cuid()


class User(SQLModel, table=True):
    id: str = Field(default_factory=_cuid.generate, primary_key=True)
    name: str
    email: str = Field(unique=True)
    google_id: str = Field(unique=True)


class EventBase(SQLModel):
    name: str
    description: str | None = None
    planned_date: date


class EventCreate(EventBase):
    pass


class Event(EventBase, table=True):
    id: str = Field(default_factory=_cuid.generate, primary_key=True)
