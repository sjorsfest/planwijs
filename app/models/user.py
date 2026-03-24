from sqlmodel import Field
from app.models.base import BaseModel


class User(BaseModel, table=True):
    name: str
    email: str = Field(unique=True)
    google_id: str = Field(unique=True)
