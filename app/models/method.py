from sqlalchemy import Column, Enum as SAEnum
from sqlmodel import Field

from app.models.base import BaseModel
from app.models.enums import Subject


class Method(BaseModel, table=True):
    slug: str = Field(unique=True, index=True)
    title: str
    subject: Subject = Field(
        default=Subject.UNKNOWN,
        sa_column=Column(SAEnum(Subject, name="subject", create_type=False), nullable=False),
    )
    url: str
