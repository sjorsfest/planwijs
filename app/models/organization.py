from sqlmodel import Field

from app.models.base import BaseModel


class Organization(BaseModel, table=True):
    __tablename__ = "organization"

    name: str
    slug: str = Field(unique=True, index=True)
